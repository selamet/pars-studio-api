from django.apps import AppConfig


class ServicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.services"

    def ready(self):
        from . import fulfilment  # noqa: F401  registers the order-item handler
