from django.core.management.base import BaseCommand

from apps.bookings.services import expire_holds


class Command(BaseCommand):
    help = "Release reservation holds whose checkout window has passed. Run from cron."

    def handle(self, *args, **options):
        count = expire_holds()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} hold(s)."))
