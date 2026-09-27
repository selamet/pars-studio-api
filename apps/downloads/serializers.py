from rest_framework import serializers

from .models import DownloadGrant


class DownloadGrantSerializer(serializers.ModelSerializer):
    file_kind_label = serializers.CharField(source="get_file_kind_display", read_only=True)
    available = serializers.BooleanField(source="is_available", read_only=True)
    remaining = serializers.SerializerMethodField()

    class Meta:
        model = DownloadGrant
        fields = [
            "id",
            "file_kind",
            "file_kind_label",
            "available",
            "remaining",
            "download_count",
            "max_downloads",
            "expires_at",
        ]

    def get_remaining(self, obj: DownloadGrant) -> int:
        return max(0, obj.max_downloads - obj.download_count)


class DownloadLinkSerializer(serializers.Serializer):
    url = serializers.URLField()
    expires_in = serializers.IntegerField()
    file_name = serializers.CharField()
