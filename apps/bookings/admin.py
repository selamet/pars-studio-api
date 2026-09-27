from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from unfold.decorators import action

from . import services
from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(ModelAdmin):
    list_display = [
        "code",
        "session_date",
        "start_time",
        "duration_hours",
        "service_type",
        "customer_name",
        "status",
        "price_usd",
        "order_link",
    ]
    list_filter = ["status", "service_type", "session_date"]
    search_fields = ["customer_name", "customer_email", "customer_phone", "artist_name"]
    date_hierarchy = "session_date"
    ordering = ["session_date", "start_time"]
    readonly_fields = [
        "code",
        "user",
        "customer_email",
        "price_usd",
        "hold_expires_at",
        "order_link",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        (None, {"fields": ("code", "status", "order_link", "price_usd")}),
        ("Session", {"fields": ("service_type", "session_date", "start_time", "duration_hours")}),
        (
            "Customer",
            {
                "fields": (
                    "user",
                    "customer_name",
                    "customer_email",
                    "customer_phone",
                    "artist_name",
                )
            },
        ),
        ("Project", {"fields": ("project_description", "reference_links", "admin_notes")}),
        ("Meta", {"fields": ("locale", "hold_expires_at", "created_at", "updated_at")}),
    )
    actions = ["confirm_selected", "cancel_selected", "complete_selected"]

    @admin.display(description="Order")
    def order_link(self, obj: Reservation) -> str:
        item = getattr(obj, "order_item", None)
        return item.order.number if item else "—"

    @action(description="Confirm (sends the confirmation email)")
    def confirm_selected(self, request, queryset):
        count = 0
        for reservation in queryset.filter(status=Reservation.Status.HOLD):
            services.confirm(reservation)
            count += 1
        self.message_user(request, f"Confirmed {count} reservation(s).", messages.SUCCESS)

    @action(description="Cancel (emails confirmed customers)")
    def cancel_selected(self, request, queryset):
        count = 0
        for reservation in queryset:
            if reservation.status in (Reservation.Status.HOLD, Reservation.Status.CONFIRMED):
                services.cancel(reservation)
                count += 1
        self.message_user(request, f"Cancelled {count} reservation(s).", messages.SUCCESS)

    @action(description="Mark as completed")
    def complete_selected(self, request, queryset):
        updated = queryset.filter(status=Reservation.Status.CONFIRMED).update(
            status=Reservation.Status.COMPLETED
        )
        self.message_user(request, f"Completed {updated} reservation(s).", messages.SUCCESS)
