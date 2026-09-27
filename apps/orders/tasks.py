from django.tasks import task

from .models import Order


@task()
def fulfil_order_task(order_id: int) -> None:
    from .fulfilment import fulfil_order

    fulfil_order(Order.objects.get(pk=order_id))
