from datetime import time

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import IntegerRangeField, RangeOperators
from django.db import models
from django.db.models import Q
from psycopg.types.range import Range

from apps.catalog.models import StudioRate
from apps.core.models import TimeStampedModel

from . import rules


class Reservation(TimeStampedModel):
    class Status(models.TextChoices):
        HOLD = "hold", "Held (awaiting payment)"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired (unpaid)"

    LIVE_STATUSES = (Status.HOLD, Status.CONFIRMED)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    artist_name = models.CharField(max_length=100, blank=True)

    service_type = models.CharField(max_length=20, choices=StudioRate.ServiceType.choices)
    session_date = models.DateField(db_index=True)
    start_time = models.TimeField()
    duration_hours = models.PositiveSmallIntegerField(
        choices=[(d, f"{d} h") for d in rules.ALL_DURATIONS]
    )
    # [start_hour, start_hour + duration) — maintained in save(), used by the exclusion constraint.
    slot = IntegerRangeField(editable=False)

    project_description = models.TextField(blank=True)
    reference_links = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.HOLD, db_index=True
    )
    admin_notes = models.TextField(blank=True)
    locale = models.CharField(max_length=5, default="en")
    price_usd = models.DecimalField(max_digits=8, decimal_places=2)
    hold_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-session_date", "-start_time"]
        constraints = [
            # Two live reservations may never overlap on the same day. Needs btree_gist.
            ExclusionConstraint(
                name="bookings_no_overlap",
                expressions=[
                    ("session_date", RangeOperators.EQUAL),
                    ("slot", RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=("hold", "confirmed")),
            ),
        ]

    def __str__(self) -> str:
        when = f"{self.session_date} {self.start_time:%H:%M}"
        return f"{self.code} · {self.get_service_type_display()} · {when}"

    @property
    def code(self) -> str:
        return f"R-{self.pk:05d}" if self.pk else "R-new"

    @property
    def start_hour(self) -> int:
        return self.start_time.hour

    @property
    def end_hour(self) -> int:
        return self.start_hour + self.duration_hours

    @property
    def end_time(self) -> time:
        return time(min(self.end_hour, 23), 0) if self.end_hour < 24 else time(23, 59)

    @property
    def is_live(self) -> bool:
        return self.status in self.LIVE_STATUSES

    def save(self, *args, **kwargs):
        self.slot = Range(self.start_hour, self.end_hour, "[)")
        super().save(*args, **kwargs)
