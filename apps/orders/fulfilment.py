"""
Turns a paid order into deliverables. Handlers are registered per item type so
later phases (services, bookings) plug in without touching this module.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Beat, BeatLicense
from apps.core.emails import send_templated_email
from apps.downloads.models import DownloadGrant

from .models import Order, OrderItem

logger = logging.getLogger(__name__)

Handler = Callable[[OrderItem], None]
HANDLERS: dict[str, Handler] = {}


def register(item_type: str):
    def decorator(func: Handler) -> Handler:
        HANDLERS[item_type] = func
        return func

    return decorator


@register(OrderItem.ItemType.BEAT_LICENSE)
def fulfil_beat_license(item: OrderItem) -> None:
    license = (
        BeatLicense.objects.select_related("beat").select_for_update().get(pk=item.beat_license_id)
    )
    beat = license.beat
    if beat.status == Beat.Status.SOLD_EXCLUSIVE and license.tier != BeatLicense.Tier.EXCLUSIVE:
        pass  # A lease bought moments before the exclusive sale is still honoured.
    elif beat.status == Beat.Status.SOLD_EXCLUSIVE:
        raise FulfilmentProblem(
            f"{beat.title}: exclusive license was already sold to another customer; "
            "refund required."
        )
    expires_at = timezone.now() + timezone.timedelta(days=settings.DOWNLOAD_GRANT_DAYS)
    for kind in license.file_kinds:
        DownloadGrant.objects.get_or_create(
            order_item=item,
            file_kind=kind,
            defaults={
                "user": item.order.user,
                "max_downloads": settings.DOWNLOAD_MAX_PER_GRANT,
                "expires_at": expires_at,
            },
        )
    if license.tier == BeatLicense.Tier.EXCLUSIVE:
        beat.mark_sold_exclusive()


class FulfilmentProblem(Exception):
    """Non-fatal: the order stays paid, the studio is told what to fix by hand."""


def fulfil_order(order: Order) -> None:
    problems: list[str] = []
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != Order.Status.PAID or order.fulfilled_at:
            return
        for item in order.items.select_related("beat_license", "service_product"):
            handler = HANDLERS.get(item.item_type)
            if handler is None:
                logger.warning(
                    "No fulfilment handler for %s (order %s)", item.item_type, order.number
                )
                continue
            try:
                handler(item)
            except FulfilmentProblem as problem:
                problems.append(str(problem))
        order.fulfilled_at = timezone.now()
        order.fulfilment_notes = "\n".join(problems)
        order.save(update_fields=["fulfilled_at", "fulfilment_notes", "updated_at"])

    send_order_emails(order, problems)


def send_order_emails(order: Order, problems: list[str], *, notify_studio: bool = True) -> None:
    """Customer confirmation in the order's language; the studio is told in Turkish."""
    context = {"order": order, "items": list(order.items.all()), "problems": problems}
    send_templated_email(
        "order_confirmation",
        {
            **context,
            "cta_url": f"{settings.FRONTEND_URL}/{order.locale}/account/orders/{order.number}",
            "cta_label": "Siparişi aç" if order.locale == "tr" else "Open your order",
        },
        [order.customer_email],
        locale=order.locale,
    )
    if notify_studio:
        send_templated_email(
            "order_notification",
            {
                **context,
                "cta_url": f"{settings.API_URL}/admin/orders/order/{order.pk}/change/",
                "cta_label": "Admin'de aç",
            },
            [settings.STUDIO_NOTIFICATION_EMAIL],
            locale="tr",
        )
