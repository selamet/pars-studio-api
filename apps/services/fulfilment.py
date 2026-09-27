from django.utils import timezone

from apps.orders.fulfilment import register
from apps.orders.models import OrderItem

from .models import ServiceOrder


@register(OrderItem.ItemType.SERVICE)
def fulfil_service(item: OrderItem) -> None:
    product = item.service_product
    ServiceOrder.objects.get_or_create(
        order_item=item,
        defaults={
            "user": item.order.user,
            "service_product": product,
            "due_at": timezone.now() + timezone.timedelta(days=product.turnaround_days),
        },
    )
