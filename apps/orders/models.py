from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    number = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    customer_email = models.EmailField()
    locale = models.CharField(max_length=5, default="en")
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    fulfilment_notes = models.TextField(
        blank=True, help_text="Problems found while fulfilling (e.g. exclusive already sold)."
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self) -> str:
        return self.number or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.number:
            # Human-readable, globally unique: PS-<year>-<zero-padded pk>.
            self.number = f"PS-{timezone.now():%Y}-{self.pk:06d}"
            super().save(update_fields=["number"])

    @property
    def is_paid(self) -> bool:
        return self.status in (self.Status.PAID, self.Status.REFUNDED)

    def recalculate(self) -> None:
        self.subtotal = sum((item.line_total for item in self.items.all()), Decimal("0.00"))
        self.total = self.subtotal
        self.save(update_fields=["subtotal", "total", "updated_at"])


class OrderItem(TimeStampedModel):
    class ItemType(models.TextChoices):
        BEAT_LICENSE = "beat_license", "Beat license"
        SERVICE = "service", "Service"
        BOOKING = "booking", "Studio booking"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    beat_license = models.ForeignKey(
        "catalog.BeatLicense",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    service_product = models.ForeignKey(
        "catalog.ServiceProduct",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # `reservation` is added in phase 5 (bookings).
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=200, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(default=1)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                name="orders_item_matches_type",
                condition=(
                    Q(
                        item_type="beat_license",
                        beat_license__isnull=False,
                        service_product__isnull=True,
                    )
                    | Q(
                        item_type="service",
                        service_product__isnull=False,
                        beat_license__isnull=True,
                    )
                    | Q(
                        item_type="booking", beat_license__isnull=True, service_product__isnull=True
                    )
                ),
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class Payment(TimeStampedModel):
    """One row per processed provider event; the unique event id makes webhooks idempotent."""

    class Type(models.TextChoices):
        CHECKOUT_COMPLETED = "checkout_completed", "Checkout completed"
        CHECKOUT_EXPIRED = "checkout_expired", "Checkout expired"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        REFUND = "refund", "Refund"
        IGNORED = "ignored", "Ignored event"

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="payments", null=True, blank=True
    )
    provider = models.CharField(max_length=20, default="stripe")
    provider_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=80)
    type = models.CharField(max_length=30, choices=Type.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_type}:{self.provider_event_id}"
