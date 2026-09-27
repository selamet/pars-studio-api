from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.storage import private_storage


class ServiceOrder(TimeStampedModel):
    """A paid mastering/mixing job: files in, work, files out, optional revisions."""

    class Status(models.TextChoices):
        AWAITING_FILES = "awaiting_files", "Awaiting files"
        RECEIVED = "received", "Files received"
        IN_PROGRESS = "in_progress", "In progress"
        DELIVERED = "delivered", "Delivered"
        REVISION_REQUESTED = "revision_requested", "Revision requested"
        COMPLETED = "completed", "Completed"

    # Who may move a job from one status to which others.
    TRANSITIONS: dict[str, dict[str, set[str]]] = {
        Status.AWAITING_FILES: {"customer": {Status.RECEIVED}, "studio": set()},
        Status.RECEIVED: {"customer": set(), "studio": {Status.IN_PROGRESS, Status.DELIVERED}},
        Status.IN_PROGRESS: {"customer": set(), "studio": {Status.DELIVERED}},
        Status.DELIVERED: {
            "customer": {Status.REVISION_REQUESTED, Status.COMPLETED},
            "studio": {Status.COMPLETED},
        },
        Status.REVISION_REQUESTED: {
            "customer": set(),
            "studio": {Status.IN_PROGRESS, Status.DELIVERED},
        },
        Status.COMPLETED: {"customer": set(), "studio": set()},
    }

    order_item = models.OneToOneField(
        "orders.OrderItem", on_delete=models.PROTECT, related_name="service_order"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_orders"
    )
    service_product = models.ForeignKey(
        "catalog.ServiceProduct", on_delete=models.PROTECT, related_name="service_orders"
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.AWAITING_FILES, db_index=True
    )
    notes = models.TextField(blank=True, help_text="Customer brief: references, loudness, vibe.")
    reference_links = models.TextField(blank=True)
    revisions_used = models.PositiveSmallIntegerField(default=0)
    due_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.service_product} for {self.user} ({self.get_status_display()})"

    @property
    def order_number(self) -> str:
        return self.order_item.order.number

    @property
    def revisions_left(self) -> int:
        return max(0, self.service_product.included_revisions - self.revisions_used)

    @property
    def accepts_uploads(self) -> bool:
        """Files may be added until the studio starts, and again after a revision request."""
        return self.status in (
            self.Status.AWAITING_FILES,
            self.Status.RECEIVED,
            self.Status.REVISION_REQUESTED,
        )

    def can_transition(self, to: str, actor: str) -> bool:
        return to in self.TRANSITIONS[self.Status(self.status)][actor]

    def transition(self, to: str, *, actor: str, by=None, message: str = "") -> "ServiceEvent":
        """Move to `to` (validated for `actor` = customer|studio), log it, and notify."""
        if not self.can_transition(to, actor):
            raise InvalidTransition(f"Cannot go from {self.status} to {to} as {actor}.")
        from_status = self.status
        now = timezone.now()
        self.status = to
        if to == self.Status.DELIVERED:
            self.delivered_at = now
        if to == self.Status.COMPLETED:
            self.completed_at = now
        if to == self.Status.REVISION_REQUESTED:
            self.revisions_used += 1
        self.save()
        event = ServiceEvent.objects.create(
            service_order=self, from_status=from_status, to_status=to, message=message, actor=by
        )
        from .notifications import notify_transition

        notify_transition(self, event, actor)
        return event


class InvalidTransition(Exception):
    pass


def service_file_path(instance: "ServiceFile", filename: str) -> str:
    return f"services/{instance.service_order_id}/{instance.direction}/{filename}"


class ServiceFile(TimeStampedModel):
    class Direction(models.TextChoices):
        CUSTOMER_UPLOAD = "customer_upload", "Customer upload"
        STUDIO_DELIVERABLE = "studio_deliverable", "Studio deliverable"

    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="files")
    direction = models.CharField(max_length=30, choices=Direction.choices)
    file = models.FileField(upload_to=service_file_path, storage=private_storage, max_length=500)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    round = models.PositiveSmallIntegerField(
        default=0, help_text="0 = original delivery, 1+ = revision rounds"
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.original_name


class ServiceEvent(models.Model):
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    message = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.from_status} → {self.to_status}"
