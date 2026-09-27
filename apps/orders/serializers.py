from rest_framework import serializers

from apps.bookings.serializers import BookingLineSerializer, ReservationSerializer
from apps.downloads.serializers import DownloadGrantSerializer

from .models import Order, OrderItem


class CheckoutItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["beat_license", "service", "booking"])
    id = serializers.IntegerField(min_value=1, required=False)
    booking = BookingLineSerializer(required=False)

    def validate(self, attrs):
        if attrs["type"] == "booking":
            if "booking" not in attrs:
                raise serializers.ValidationError({"booking": "Booking details are required."})
        elif "id" not in attrs:
            raise serializers.ValidationError({"id": "This field is required."})
        return attrs


class CheckoutSerializer(serializers.Serializer):
    items = CheckoutItemSerializer(many=True, min_length=1, max_length=20)
    locale = serializers.ChoiceField(choices=["en", "tr"], default="en")

    def validate_items(self, items):
        seen = set()
        for item in items:
            key = (item["type"], item.get("id"), str(item.get("booking", "")))
            if key in seen:
                raise serializers.ValidationError("Duplicate item in cart.")
            seen.add(key)
        return items


class CheckoutResponseSerializer(serializers.Serializer):
    order_number = serializers.CharField()
    checkout_url = serializers.URLField()


class OrderItemSerializer(serializers.ModelSerializer):
    beat_slug = serializers.CharField(source="beat_license.beat.slug", read_only=True, default=None)
    license_tier = serializers.CharField(source="beat_license.tier", read_only=True, default=None)
    service_slug = serializers.CharField(
        source="service_product.slug", read_only=True, default=None
    )
    downloads = DownloadGrantSerializer(source="download_grants", many=True, read_only=True)
    reservation = ReservationSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "item_type",
            "title",
            "description",
            "unit_price",
            "quantity",
            "line_total",
            "beat_slug",
            "license_tier",
            "service_slug",
            "downloads",
            "reservation",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "status_label",
            "currency",
            "subtotal",
            "total",
            "locale",
            "created_at",
            "paid_at",
            "expires_at",
            "items",
        ]
