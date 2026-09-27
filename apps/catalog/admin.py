from django.contrib import admin, messages
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from .models import Beat, BeatLicense, ServiceProduct, StudioRate


class BeatLicenseInline(TabularInline):
    model = BeatLicense
    extra = 0
    fields = ["tier", "price_usd", "is_active", "mp3_file", "wav_file", "stems_zip", "terms"]
    ordering = ["price_usd"]


@admin.register(Beat)
class BeatAdmin(ModelAdmin):
    inlines = [BeatLicenseInline]
    list_display = ["title", "status", "bpm", "key", "genre", "license_count", "published_at"]
    list_filter = ["status", "genre", "key"]
    search_fields = ["title", "slug", "tags"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["published_at", "created_at", "updated_at"]
    actions = ["publish", "unpublish"]
    fieldsets = (
        (None, {"fields": ("title", "slug", "status", "published_at")}),
        ("Music", {"fields": ("bpm", "key", "genre", "tags", "duration_seconds")}),
        ("Copy", {"fields": ("description", "description_tr")}),
        ("Media", {"fields": ("cover", "preview")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Licenses")
    def license_count(self, obj: Beat) -> str:
        active = obj.licenses.filter(is_active=True).count()
        return f"{active}/{obj.licenses.count()}"

    @action(description="Publish selected beats")
    def publish(self, request, queryset):
        skipped = 0
        for beat in queryset:
            if beat.status == Beat.Status.SOLD_EXCLUSIVE:
                skipped += 1
                continue
            beat.status = Beat.Status.PUBLISHED
            beat.published_at = beat.published_at or timezone.now()
            beat.save(update_fields=["status", "published_at", "updated_at"])
        published = queryset.count() - skipped
        self.message_user(request, f"Published {published} beat(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request, f"Skipped {skipped} beat(s) already sold exclusively.", messages.WARNING
            )

    @action(description="Unpublish selected beats")
    def unpublish(self, request, queryset):
        updated = queryset.exclude(status=Beat.Status.SOLD_EXCLUSIVE).update(
            status=Beat.Status.DRAFT
        )
        self.message_user(request, f"Unpublished {updated} beat(s).", messages.SUCCESS)


@admin.register(ServiceProduct)
class ServiceProductAdmin(ModelAdmin):
    list_display = [
        "name",
        "kind",
        "price_usd",
        "turnaround_days",
        "included_revisions",
        "is_active",
    ]
    list_filter = ["kind", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["name", "name_tr", "slug"]
    prepopulated_fields = {"slug": ["name"]}
    ordering = ["sort_order"]
    fieldsets = (
        (None, {"fields": ("name", "name_tr", "slug", "kind", "is_active", "sort_order")}),
        (
            "Pricing & scope",
            {"fields": ("price_usd", "turnaround_days", "included_revisions", "max_stems")},
        ),
        ("Copy", {"fields": ("description", "description_tr")}),
    )


@admin.register(StudioRate)
class StudioRateAdmin(ModelAdmin):
    list_display = ["service_type", "hourly_price_usd", "is_active"]
    list_editable = ["hourly_price_usd", "is_active"]
