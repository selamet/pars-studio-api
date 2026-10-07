from django.conf import settings

from apps.core.emails import send_templated_email

CUSTOMER_STATUSES = {"in_progress", "delivered", "completed"}
STUDIO_STATUSES = {"received", "revision_requested", "completed"}

STATUS_LABELS_TR = {
    "awaiting_files": "Dosyalar bekleniyor",
    "received": "Dosyalar alındı",
    "in_progress": "Çalışılıyor",
    "delivered": "Teslim edildi",
    "revision_requested": "Revizyon istendi",
    "completed": "Tamamlandı",
}


def _context(service_order, event, locale: str) -> dict:
    product = service_order.service_product
    status_label = service_order.get_status_display()
    product_name = product.name
    if locale == "tr":
        status_label = STATUS_LABELS_TR.get(service_order.status, status_label)
        product_name = product.name_tr or product_name
    return {
        "service_order": service_order,
        "event": event,
        "status_label": status_label,
        "product_name": product_name,
        "order_number": service_order.order_number,
    }


def notify_transition(service_order, event, actor: str) -> None:
    locale = service_order.order_item.order.locale
    if event.to_status in CUSTOMER_STATUSES and actor == "studio":
        send_templated_email(
            "service_status",
            {
                **_context(service_order, event, locale),
                "cta_url": f"{settings.FRONTEND_URL}/{locale}/account/services/{service_order.id}",
                "cta_label": "Siparişi aç" if locale == "tr" else "Open your order",
            },
            [service_order.user.email],
            locale=locale,
        )
    if event.to_status in STUDIO_STATUSES and actor == "customer":
        send_templated_email(
            "service_notification",
            {
                **_context(service_order, event, "tr"),
                "cta_url": (
                    f"{settings.API_URL}/admin/services/serviceorder/{service_order.pk}/change/"
                ),
                "cta_label": "Admin'de aç",
            },
            [settings.STUDIO_NOTIFICATION_EMAIL],
            locale="tr",
        )
