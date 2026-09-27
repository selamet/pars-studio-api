from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import DownloadGrant


@admin.register(DownloadGrant)
class DownloadGrantAdmin(ModelAdmin):
    list_display = [
        "order_item",
        "user",
        "file_kind",
        "download_count",
        "max_downloads",
        "expires_at",
        "revoked",
    ]
    list_filter = ["file_kind", "revoked"]
    search_fields = ["user__email", "order_item__order__number", "order_item__title"]
    list_editable = ["max_downloads", "expires_at", "revoked"]
    readonly_fields = ["order_item", "user", "file_kind", "download_count", "last_downloaded_at"]
