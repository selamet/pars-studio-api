"""Stripe webhook handling. Every event is recorded once; replays are no-ops."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Order, Payment
from .services import release_holds
from .tasks import fulfil_order_task

logger = logging.getLogger(__name__)


class InvalidWebhook(Exception):
    pass


def parse_event(payload: bytes, signature: str) -> dict:
    """Verify the signature, then hand back the plain JSON event (StripeObject is dict-hostile)."""
    try:
        stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise InvalidWebhook(str(exc)) from exc
    return json.loads(payload)


def _order_for_session(session) -> Order | None:
    order_id = (session.get("metadata") or {}).get("order_id")
    if order_id:
        return Order.objects.filter(pk=order_id).first()
    return Order.objects.filter(stripe_checkout_session_id=session["id"]).first()


def handle_event(event: dict) -> Payment | None:
    """Apply one event. Raises DuplicateEvent when the event id was already recorded."""
    obj = event["data"]["object"]
    event_type = event["type"]
    order: Order | None = None
    payment_type = Payment.Type.IGNORED
    amount: Decimal | None = None
    after_commit = None

    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        order = _order_for_session(obj)
        if order and obj.get("payment_status") == "paid" and order.status == Order.Status.PENDING:
            payment_type = Payment.Type.CHECKOUT_COMPLETED
            amount = Decimal(obj.get("amount_total") or 0) / 100
            order.status = Order.Status.PAID
            order.paid_at = timezone.now()
            order.stripe_payment_intent_id = str(obj.get("payment_intent") or "")
            order.save(
                update_fields=["status", "paid_at", "stripe_payment_intent_id", "updated_at"]
            )
            after_commit = lambda: fulfil_order_task.enqueue(order.pk)  # noqa: E731
    elif event_type == "checkout.session.expired":
        order = _order_for_session(obj)
        if order and order.status == Order.Status.PENDING:
            payment_type = Payment.Type.CHECKOUT_EXPIRED
            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])
            release_holds(order)
    elif event_type == "checkout.session.async_payment_failed":
        order = _order_for_session(obj)
        if order and order.status == Order.Status.PENDING:
            payment_type = Payment.Type.PAYMENT_FAILED
            order.status = Order.Status.FAILED
            order.save(update_fields=["status", "updated_at"])
            release_holds(order)
    elif event_type == "charge.refunded":
        intent = obj.get("payment_intent")
        order = Order.objects.filter(stripe_payment_intent_id=intent).first() if intent else None
        if order and order.status == Order.Status.PAID and obj.get("refunded"):
            payment_type = Payment.Type.REFUND
            amount = Decimal(obj.get("amount_refunded") or 0) / 100
            order.status = Order.Status.REFUNDED
            order.save(update_fields=["status", "updated_at"])
            from apps.bookings import services as booking_services
            from apps.downloads.models import DownloadGrant

            DownloadGrant.objects.filter(order_item__order=order).update(revoked=True)
            for item in order.items.filter(reservation__isnull=False).select_related("reservation"):
                booking_services.cancel(item.reservation)

    try:
        payment = Payment.objects.create(
            order=order,
            provider_event_id=event["id"],
            event_type=event_type,
            type=payment_type,
            amount=amount,
            raw={"id": event["id"], "type": event_type, "object": obj.get("id")},
        )
    except IntegrityError:
        # Duplicate delivery: the outer transaction rolls back the state changes above.
        raise DuplicateEvent(event["id"]) from None

    if after_commit:
        transaction.on_commit(after_commit)
    return payment


class DuplicateEvent(Exception):
    pass


def process(payload: bytes, signature: str) -> None:
    event = parse_event(payload, signature)
    try:
        with transaction.atomic():
            handle_event(event)
    except DuplicateEvent:
        logger.info("Stripe event %s already processed", event["id"])
