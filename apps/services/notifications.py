from django.conf import settings

from apps.core.emails import send_templated_email

CUSTOMER_STATUSES = {"in_progress", "delivered", "completed"}
STUDIO_STATUSES = {"received", "revision_requested", "completed"}


def notify_transition(service_order, event, actor: str) -> None:
    context = {
        "service_order": service_order,
        "event": event,
        "status_label": service_order.get_status_display(),
        "order_number": service_order.order_number,
        "locale": service_order.order_item.order.locale,
    }
    if event.to_status in CUSTOMER_STATUSES and actor == "studio":
        send_templated_email("service_status", context, [service_order.user.email])
    if event.to_status in STUDIO_STATUSES and actor == "customer":
        send_templated_email("service_notification", context, [settings.STUDIO_NOTIFICATION_EMAIL])
