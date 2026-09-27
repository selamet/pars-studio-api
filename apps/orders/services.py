"""Checkout: validate cart lines against the database and open a Stripe session."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings import services as booking_services
from apps.bookings.models import Reservation
from apps.catalog.models import Beat, BeatLicense, ServiceProduct

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """A cart line cannot be sold. `code` is stable for the frontend, `line` the bad input."""

    def __init__(self, code: str, message: str, line: dict | None = None):
        super().__init__(message)
        self.code = code
        self.line = line


@dataclass
class Line:
    item_type: str
    title: str
    description: str
    unit_price: object
    beat_license: BeatLicense | None = None
    service_product: ServiceProduct | None = None
    reservation: Reservation | None = None


def _resolve_line(raw: dict, user, locale: str, hold_until) -> Line:
    if raw["type"] == "beat_license":
        try:
            license = (
                BeatLicense.objects.select_related("beat")
                .select_for_update(of=("self",))
                .get(pk=raw["id"], is_active=True)
            )
        except BeatLicense.DoesNotExist as exc:
            raise CheckoutError("unavailable", "This license is no longer available.", raw) from exc
        if license.beat.status != Beat.Status.PUBLISHED:
            raise CheckoutError("unavailable", "This beat is no longer for sale.", raw)
        return Line(
            item_type=OrderItem.ItemType.BEAT_LICENSE,
            title=f"{license.beat.title} — {license.get_tier_display()}",
            description=", ".join(kind.upper() for kind in license.file_kinds),
            unit_price=license.price_usd,
            beat_license=license,
        )
    if raw["type"] == "service":
        try:
            product = ServiceProduct.objects.get(pk=raw["id"], is_active=True)
        except ServiceProduct.DoesNotExist as exc:
            raise CheckoutError("unavailable", "This service is no longer available.", raw) from exc
        return Line(
            item_type=OrderItem.ItemType.SERVICE,
            title=product.name,
            description=product.get_kind_display(),
            unit_price=product.price_usd,
            service_product=product,
        )
    if raw["type"] == "booking":
        try:
            reservation = booking_services.create_hold(
                user, raw["booking"], hold_until=hold_until, locale=locale
            )
        except booking_services.BookingError as exc:
            raise CheckoutError(exc.code, str(exc), _public_line(raw)) from exc
        return Line(
            item_type=OrderItem.ItemType.BOOKING,
            title=(
                f"Studio session — {reservation.get_service_type_display()} · "
                f"{reservation.session_date:%Y-%m-%d} {reservation.start_time:%H:%M}"
            ),
            description=f"{reservation.duration_hours} h · #{reservation.code}",
            unit_price=reservation.price_usd,
            reservation=reservation,
        )
    raise CheckoutError("invalid", "Unknown item type.", raw)


def _public_line(raw: dict) -> dict:
    """What we echo back on errors: enough to identify the cart line, no PII."""
    if raw["type"] == "booking":
        b = raw["booking"]
        return {
            "type": "booking",
            "service_type": b["service_type"],
            "session_date": str(b["session_date"]),
            "start_time": b["start_time"].strftime("%H:%M"),
            "duration_hours": b["duration_hours"],
        }
    return {"type": raw["type"], "id": raw["id"]}


@transaction.atomic
def build_order(user, raw_items: list[dict], locale: str) -> Order:
    """Create a pending order from cart lines. Prices always come from the database."""
    hold_until = timezone.now() + timedelta(minutes=settings.CHECKOUT_SESSION_TTL_MINUTES)
    lines = [_resolve_line(raw, user, locale, hold_until) for raw in raw_items]
    exclusive_beats = {
        line.beat_license.beat_id
        for line in lines
        if line.beat_license and line.beat_license.tier == BeatLicense.Tier.EXCLUSIVE
    }
    for line in lines:
        if (
            line.beat_license
            and line.beat_license.beat_id in exclusive_beats
            and line.beat_license.tier != BeatLicense.Tier.EXCLUSIVE
        ):
            raise CheckoutError(
                "invalid", "An exclusive license already covers this beat; remove the lease."
            )

    order = Order.objects.create(user=user, customer_email=user.email, locale=locale)
    for line in lines:
        OrderItem.objects.create(
            order=order,
            item_type=line.item_type,
            title=line.title,
            description=line.description,
            unit_price=line.unit_price,
            beat_license=line.beat_license,
            service_product=line.service_product,
            reservation=line.reservation,
        )
    order.recalculate()
    return order


def release_holds(order: Order, *, to=Reservation.Status.EXPIRED) -> None:
    """Free the studio slots held by an order that will not be paid."""
    for item in order.items.filter(reservation__isnull=False).select_related("reservation"):
        booking_services.release_hold(item.reservation, to=to)


def create_checkout_session(order: Order) -> str:
    """Open a hosted Stripe Checkout session for the order and return its URL."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    ttl = timedelta(minutes=settings.CHECKOUT_SESSION_TTL_MINUTES)
    expires_at = timezone.now() + ttl
    site = settings.FRONTEND_URL
    session = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=order.number,
        customer_email=order.customer_email,
        line_items=[
            {
                "quantity": item.quantity,
                "price_data": {
                    "currency": order.currency.lower(),
                    "unit_amount": int(item.unit_price * 100),
                    "product_data": {
                        "name": item.title,
                        **({"description": item.description} if item.description else {}),
                    },
                },
            }
            for item in order.items.all()
        ],
        metadata={"order_id": str(order.pk), "order_number": order.number},
        success_url=f"{site}/{order.locale}/checkout/success?order={order.number}",
        cancel_url=f"{site}/{order.locale}/cart?cancelled={order.number}",
        expires_at=int(expires_at.timestamp()),
        locale="auto",
    )
    order.stripe_checkout_session_id = session.id
    order.expires_at = expires_at
    order.save(update_fields=["stripe_checkout_session_id", "expires_at", "updated_at"])
    return session.url


def expire_pending_orders(now=None) -> int:
    """Cancel pending orders whose Stripe session is past its expiry. Returns the count."""
    now = now or timezone.now()
    stale = Order.objects.filter(status=Order.Status.PENDING, expires_at__lt=now)
    count = 0
    for order in stale:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        release_holds(order)
        count += 1
    if count:
        logger.info("Expired %d pending order(s)", count)
    return count
