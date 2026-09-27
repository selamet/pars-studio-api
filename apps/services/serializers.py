from rest_framework import serializers

from .models import ServiceEvent, ServiceFile, ServiceOrder


class ServiceFileSerializer(serializers.ModelSerializer):
    direction_label = serializers.CharField(source="get_direction_display", read_only=True)

    class Meta:
        model = ServiceFile
        fields = [
            "id",
            "direction",
            "direction_label",
            "original_name",
            "size",
            "content_type",
            "round",
            "created_at",
        ]


class ServiceEventSerializer(serializers.ModelSerializer):
    to_status_label = serializers.SerializerMethodField()
    by_studio = serializers.SerializerMethodField()

    class Meta:
        model = ServiceEvent
        fields = [
            "id",
            "from_status",
            "to_status",
            "to_status_label",
            "message",
            "by_studio",
            "created_at",
        ]

    def get_to_status_label(self, obj: ServiceEvent) -> str:
        return ServiceOrder.Status(obj.to_status).label

    def get_by_studio(self, obj: ServiceEvent) -> bool:
        return bool(obj.actor and obj.actor.is_staff)


class ServiceOrderSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    order_number = serializers.CharField(read_only=True)
    product_name = serializers.CharField(source="service_product.name", read_only=True)
    product_kind = serializers.CharField(source="service_product.kind", read_only=True)
    included_revisions = serializers.IntegerField(
        source="service_product.included_revisions", read_only=True
    )
    max_files = serializers.IntegerField(source="service_product.max_stems", read_only=True)
    revisions_left = serializers.IntegerField(read_only=True)
    accepts_uploads = serializers.BooleanField(read_only=True)
    files = ServiceFileSerializer(many=True, read_only=True)
    events = ServiceEventSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceOrder
        fields = [
            "id",
            "order_number",
            "product_name",
            "product_kind",
            "status",
            "status_label",
            "notes",
            "reference_links",
            "included_revisions",
            "revisions_used",
            "revisions_left",
            "max_files",
            "accepts_uploads",
            "due_at",
            "delivered_at",
            "completed_at",
            "created_at",
            "files",
            "events",
        ]
        read_only_fields = [f for f in fields if f not in ("notes", "reference_links")]


class PresignRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )


class PresignResponseSerializer(serializers.Serializer):
    direct = serializers.BooleanField()
    key = serializers.CharField()
    upload_url = serializers.CharField()
    method = serializers.CharField()
    headers = serializers.DictField(child=serializers.CharField())


class ConfirmUploadSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=500)
    file_name = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )


class LocalUploadSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=500)
    file = serializers.FileField()


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
