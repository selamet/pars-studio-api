from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class DownloadGrant(TimeStampedModel):
    """Right to download one deliverable of a purchased license, N times, until a date."""

    class FileKind(models.TextChoices):
        MP3 = "mp3", "MP3"
        WAV = "wav", "WAV"
        STEMS = "stems", "Stems (ZIP)"

    order_item = models.ForeignKey(
        "orders.OrderItem", on_delete=models.CASCADE, related_name="download_grants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="download_grants"
    )
    file_kind = models.CharField(max_length=10, choices=FileKind.choices)
    download_count = models.PositiveIntegerField(default=0)
    max_downloads = models.PositiveIntegerField(default=10)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order_item", "file_kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["order_item", "file_kind"], name="downloads_one_grant_per_kind"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_item} [{self.file_kind}]"

    @property
    def is_available(self) -> bool:
        return (
            not self.revoked
            and self.expires_at > timezone.now()
            and self.download_count < self.max_downloads
        )

    @property
    def file(self):
        license = self.order_item.beat_license
        return license.file_for(self.file_kind) if license else None
