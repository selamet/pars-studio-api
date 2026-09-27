from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"

    def ready(self):
        from . import fulfilment  # noqa: F401  registers the booking order-item handler
