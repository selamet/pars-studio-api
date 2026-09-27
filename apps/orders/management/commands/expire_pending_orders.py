from django.core.management.base import BaseCommand

from apps.orders.services import expire_pending_orders


class Command(BaseCommand):
    help = "Cancel pending orders whose Stripe Checkout session has expired. Run from cron."

    def handle(self, *args, **options):
        count = expire_pending_orders()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} order(s)."))
