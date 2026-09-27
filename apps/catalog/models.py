from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel
from apps.core.storage import private_storage, public_storage


class BeatQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Beat.Status.PUBLISHED)

    def purchasable(self):
        return self.published().filter(licenses__is_active=True).distinct()


class Beat(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SOLD_EXCLUSIVE = "sold_exclusive", "Sold (exclusive)"

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    bpm = models.PositiveSmallIntegerField()
    key = models.CharField(max_length=8, blank=True, help_text="Musical key, e.g. Am, F#m, C")
    genre = models.CharField(max_length=60, blank=True)
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    description = models.TextField(blank=True)
    description_tr = models.TextField(
        blank=True, help_text="Turkish description; falls back to English."
    )
    cover = models.ImageField(upload_to="beats/covers/", storage=public_storage, blank=True)
    preview = models.FileField(
        upload_to="beats/previews/",
        storage=public_storage,
        blank=True,
        help_text="Tagged MP3 played on the storefront.",
    )
    duration_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)

    objects = BeatQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["genre"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:170]
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def is_purchasable(self) -> bool:
        return self.status == self.Status.PUBLISHED

    def mark_sold_exclusive(self) -> None:
        """Called when an exclusive license is bought: nothing on this beat sells any more."""
        self.status = self.Status.SOLD_EXCLUSIVE
        self.save(update_fields=["status", "updated_at"])
        self.licenses.update(is_active=False)


class BeatLicense(TimeStampedModel):
    class Tier(models.TextChoices):
        MP3_LEASE = "mp3_lease", "MP3 Lease"
        WAV_LEASE = "wav_lease", "WAV Lease"
        TRACKOUT = "trackout", "Trackout (stems)"
        EXCLUSIVE = "exclusive", "Exclusive"

    # Which deliverables each tier ships with. Files must exist on the license.
    TIER_FILE_KINDS = {
        Tier.MP3_LEASE: ("mp3",),
        Tier.WAV_LEASE: ("mp3", "wav"),
        Tier.TRACKOUT: ("mp3", "wav", "stems"),
        Tier.EXCLUSIVE: ("mp3", "wav", "stems"),
    }

    beat = models.ForeignKey(Beat, on_delete=models.CASCADE, related_name="licenses")
    tier = models.CharField(max_length=20, choices=Tier.choices)
    price_usd = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    is_active = models.BooleanField(default=True)
    terms = models.TextField(blank=True, help_text="License terms shown before purchase.")
    mp3_file = models.FileField(upload_to="beats/files/", storage=private_storage, blank=True)
    wav_file = models.FileField(upload_to="beats/files/", storage=private_storage, blank=True)
    stems_zip = models.FileField(upload_to="beats/files/", storage=private_storage, blank=True)

    class Meta:
        ordering = ["price_usd"]
        constraints = [
            models.UniqueConstraint(fields=["beat", "tier"], name="catalog_one_license_per_tier"),
        ]

    def __str__(self) -> str:
        return f"{self.beat} — {self.get_tier_display()}"

    @property
    def file_kinds(self) -> tuple[str, ...]:
        return self.TIER_FILE_KINDS[self.Tier(self.tier)]

    def file_for(self, kind: str):
        return {"mp3": self.mp3_file, "wav": self.wav_file, "stems": self.stems_zip}[kind]

    @property
    def missing_files(self) -> list[str]:
        return [kind for kind in self.file_kinds if not self.file_for(kind)]


class ServiceProduct(TimeStampedModel):
    class Kind(models.TextChoices):
        MASTERING = "mastering", "Mastering"
        MIXING = "mixing", "Mixing"

    name = models.CharField(max_length=120)
    name_tr = models.CharField(
        max_length=120, blank=True, help_text="Turkish name; falls back to name."
    )
    slug = models.SlugField(max_length=140, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    price_usd = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    turnaround_days = models.PositiveSmallIntegerField(default=5)
    included_revisions = models.PositiveSmallIntegerField(default=1)
    max_stems = models.PositiveSmallIntegerField(
        default=1, help_text="How many source files the customer may upload."
    )
    description = models.TextField(blank=True)
    description_tr = models.TextField(
        blank=True, help_text="Turkish description; falls back to English."
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price_usd"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:130]
        super().save(*args, **kwargs)


class StudioRate(TimeStampedModel):
    """Hourly studio price per session type; reservations are priced from this."""

    class ServiceType(models.TextChoices):
        RECORDING = "recording", "Recording"
        MIXING = "mixing", "Mixing session"
        MASTERING = "mastering", "Mastering session"
        BEAT = "beat", "Beat production"
        VOCAL = "vocal", "Vocal production"

    service_type = models.CharField(max_length=20, choices=ServiceType.choices, unique=True)
    hourly_price_usd = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service_type"]

    def __str__(self) -> str:
        return f"{self.get_service_type_display()} — ${self.hourly_price_usd}/h"
