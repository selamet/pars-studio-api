from rest_framework import serializers

from apps.catalog.models import StudioRate

from . import rules
from .models import Reservation


class BookingConfigSerializer(serializers.Serializer):
    open_hour = serializers.IntegerField()
    close_hour = serializers.IntegerField()
    closed_weekdays = serializers.ListField(child=serializers.IntegerField())
    max_advance_days = serializers.IntegerField()
    hold_minutes = serializers.IntegerField()
    durations = serializers.DictField(child=serializers.ListField(child=serializers.IntegerField()))
    service_types = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField())
    )


class AvailabilitySlotSerializer(serializers.Serializer):
    start = serializers.CharField()
    durations = serializers.ListField(child=serializers.IntegerField())


class AvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    service_type = serializers.CharField()
    closed = serializers.BooleanField()
    slots = AvailabilitySlotSerializer(many=True)


class BookingLineSerializer(serializers.Serializer):
    """Fields a `booking` cart line must carry into checkout."""

    service_type = serializers.ChoiceField(choices=StudioRate.ServiceType.choices)
    session_date = serializers.DateField()
    start_time = serializers.TimeField()
    duration_hours = serializers.ChoiceField(choices=rules.ALL_DURATIONS)
    customer_name = serializers.CharField(max_length=100)
    customer_phone = serializers.CharField(max_length=20)
    artist_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    project_description = serializers.CharField(required=False, allow_blank=True, default="")
    reference_links = serializers.CharField(required=False, allow_blank=True, default="")


class ReservationSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)
    service_type_label = serializers.CharField(source="get_service_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    end_time = serializers.TimeField(read_only=True)
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "code",
            "service_type",
            "service_type_label",
            "session_date",
            "start_time",
            "end_time",
            "duration_hours",
            "status",
            "status_label",
            "price_usd",
            "customer_name",
            "artist_name",
            "project_description",
            "reference_links",
            "hold_expires_at",
            "order_number",
            "created_at",
        ]

    def get_order_number(self, obj: Reservation) -> str | None:
        item = getattr(obj, "order_item", None)
        return item.order.number if item else None
