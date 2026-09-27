from apps.orders.fulfilment import register
from apps.orders.models import OrderItem

from . import services


@register(OrderItem.ItemType.BOOKING)
def fulfil_booking(item: OrderItem) -> None:
    if item.reservation_id:
        services.confirm(item.reservation)
