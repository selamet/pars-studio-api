from django import forms
from django.contrib import admin, messages
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import action

from .models import InvalidTransition, ServiceEvent, ServiceFile, ServiceOrder


class DeliverableInline(StackedInline):
    """Studio uploads results here; customer uploads are listed read-only below."""

    model = ServiceFile
    fk_name = "service_order"
    extra = 0
    verbose_name = "deliverable"
    verbose_name_plural = "Deliverables (studio → customer)"
    fields = ["file", "original_name", "round"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request).filter(direction=ServiceFile.Direction.STUDIO_DELIVERABLE)
        )


class CustomerFileInline(TabularInline):
    model = ServiceFile
    fk_name = "service_order"
    extra = 0
    can_delete = False
    verbose_name_plural = "Customer uploads"
    fields = ["original_name", "size", "content_type", "round", "created_at"]
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).filter(direction=ServiceFile.Direction.CUSTOMER_UPLOAD)

    def has_add_permission(self, request, obj=None):
        return False


class EventInline(TabularInline):
    model = ServiceEvent
    extra = 0
    can_delete = False
    fields = ["created_at", "from_status", "to_status", "actor", "message"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class DeliverForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea, required=False)


@admin.register(ServiceOrder)
class ServiceOrderAdmin(ModelAdmin):
    inlines = [DeliverableInline, CustomerFileInline, EventInline]
    list_display = ["__str__", "order_number", "status", "due_at", "revisions_used", "created_at"]
    list_filter = ["status", "service_product"]
    search_fields = ["user__email", "order_item__order__number", "service_product__name"]
    readonly_fields = [
        "order_item",
        "user",
        "service_product",
        "status",
        "revisions_used",
        "delivered_at",
        "completed_at",
        "created_at",
    ]
    fields = [
        "order_item",
        "user",
        "service_product",
        "status",
        "due_at",
        "notes",
        "reference_links",
        "revisions_used",
        "delivered_at",
        "completed_at",
        "created_at",
    ]
    actions = ["start_work", "deliver", "complete"]

    def save_formset(self, request, form, formset, change):
        # Anything added through the deliverable inline is a studio deliverable.
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, ServiceFile) and not obj.pk:
                obj.direction = ServiceFile.Direction.STUDIO_DELIVERABLE
                obj.uploaded_by = request.user
                if not obj.original_name:
                    obj.original_name = obj.file.name.rsplit("/", 1)[-1]
                obj.size = obj.file.size
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    def _run(self, request, queryset, to: str, label: str):
        done = 0
        for service_order in queryset:
            try:
                service_order.transition(to, actor="studio", by=request.user)
                done += 1
            except InvalidTransition as exc:
                self.message_user(request, f"{service_order}: {exc}", messages.WARNING)
        self.message_user(request, f"{label}: {done} order(s).", messages.SUCCESS)

    @action(description="Mark as in progress")
    def start_work(self, request, queryset):
        self._run(request, queryset, ServiceOrder.Status.IN_PROGRESS, "Started")

    @action(description="Mark as delivered (customer is emailed)")
    def deliver(self, request, queryset):
        missing = [
            so for so in queryset if not so.files.filter(direction="studio_deliverable").exists()
        ]
        for so in missing:
            self.message_user(request, f"{so}: upload a deliverable first.", messages.ERROR)
        self._run(
            request,
            queryset.exclude(pk__in=[so.pk for so in missing]),
            ServiceOrder.Status.DELIVERED,
            "Delivered",
        )

    @action(description="Mark as completed")
    def complete(self, request, queryset):
        self._run(request, queryset, ServiceOrder.Status.COMPLETED, "Completed")
