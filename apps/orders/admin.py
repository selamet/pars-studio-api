from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from apps.downloads.models import DownloadGrant

from .fulfilment import send_order_emails
from .models import Order, OrderItem, Payment


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ["item_type", "title", "description", "unit_price", "quantity", "line_total"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ["created_at", "event_type", "type", "amount", "provider_event_id"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    inlines = [OrderItemInline, PaymentInline]
    list_display = [
        "number",
        "customer_email",
        "status",
        "total",
        "created_at",
        "paid_at",
        "has_problems",
    ]
    list_filter = ["status", "locale", "created_at"]
    search_fields = [
        "number",
        "customer_email",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
    ]
    readonly_fields = [
        "number",
        "user",
        "customer_email",
        "currency",
        "subtotal",
        "total",
        "locale",
        "stripe_links",
        "expires_at",
        "paid_at",
        "fulfilled_at",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        (None, {"fields": ("number", "status", "user", "customer_email", "locale")}),
        ("Amounts", {"fields": ("currency", "subtotal", "total")}),
        ("Stripe", {"fields": ("stripe_links", "expires_at", "paid_at")}),
        ("Fulfilment", {"fields": ("fulfilled_at", "fulfilment_notes")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    actions = ["resend_confirmation", "extend_downloads"]

    @admin.display(description="Attention", boolean=True)
    def has_problems(self, obj: Order) -> bool:
        return bool(obj.fulfilment_notes)

    @admin.display(description="Stripe")
    def stripe_links(self, obj: Order):
        parts = []
        if obj.stripe_payment_intent_id:
            parts.append(
                format_html(
                    '<a href="https://dashboard.stripe.com/payments/{}" target="_blank">'
                    "Payment {}</a>",
                    obj.stripe_payment_intent_id,
                    obj.stripe_payment_intent_id,
                )
            )
        if obj.stripe_checkout_session_id:
            parts.append(format_html("Session <code>{}</code>", obj.stripe_checkout_session_id))
        return format_html(" · ".join(["{}"] * len(parts)), *parts) if parts else "—"

    @action(description="Resend order confirmation email")
    def resend_confirmation(self, request, queryset):
        sent = 0
        for order in queryset.filter(status=Order.Status.PAID):
            send_order_emails(order, [], notify_studio=False)
            sent += 1
        self.message_user(request, f"Queued {sent} confirmation email(s).", messages.SUCCESS)

    @action(description="Extend download links by 30 days")
    def extend_downloads(self, request, queryset):
        grants = DownloadGrant.objects.filter(order_item__order__in=queryset)
        updated = 0
        for grant in grants:
            grant.expires_at = max(grant.expires_at, timezone.now()) + timezone.timedelta(days=30)
            grant.revoked = False
            grant.save(update_fields=["expires_at", "revoked", "updated_at"])
            updated += 1
        self.message_user(request, f"Extended {updated} download grant(s).", messages.SUCCESS)


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ["created_at", "order", "event_type", "type", "amount", "provider_event_id"]
    list_filter = ["type", "event_type"]
    search_fields = ["provider_event_id", "order__number"]
    readonly_fields = [
        "order",
        "provider",
        "provider_event_id",
        "event_type",
        "type",
        "amount",
        "raw",
    ]
