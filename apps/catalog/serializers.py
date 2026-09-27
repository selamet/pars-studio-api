from rest_framework import serializers

from .models import Beat, BeatLicense, ServiceProduct, StudioRate


def _public_url(file) -> str | None:
    return file.url if file else None


class BeatLicenseSerializer(serializers.ModelSerializer):
    tier_label = serializers.CharField(source="get_tier_display", read_only=True)
    includes = serializers.SerializerMethodField()

    class Meta:
        model = BeatLicense
        fields = ["id", "tier", "tier_label", "price_usd", "includes", "terms"]

    def get_includes(self, obj: BeatLicense) -> list[str]:
        # Never leak the private file names; only say what the buyer receives.
        return list(obj.file_kinds)


class BeatListSerializer(serializers.ModelSerializer):
    cover_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    min_price_usd = serializers.SerializerMethodField()

    class Meta:
        model = Beat
        fields = [
            "id",
            "slug",
            "title",
            "bpm",
            "key",
            "genre",
            "tags",
            "duration_seconds",
            "cover_url",
            "preview_url",
            "min_price_usd",
            "published_at",
        ]

    def get_cover_url(self, obj: Beat) -> str | None:
        return _public_url(obj.cover)

    def get_preview_url(self, obj: Beat) -> str | None:
        return _public_url(obj.preview)

    def get_min_price_usd(self, obj: Beat) -> str | None:
        prices = [lic.price_usd for lic in obj.licenses.all() if lic.is_active]
        return str(min(prices)) if prices else None


class BeatDetailSerializer(BeatListSerializer):
    licenses = serializers.SerializerMethodField()

    class Meta(BeatListSerializer.Meta):
        fields = BeatListSerializer.Meta.fields + ["description", "licenses"]

    def get_licenses(self, obj: Beat) -> list[dict]:
        active = [lic for lic in obj.licenses.all() if lic.is_active]
        return BeatLicenseSerializer(active, many=True).data


class ServiceProductSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = ServiceProduct
        fields = [
            "id",
            "slug",
            "name",
            "kind",
            "kind_label",
            "price_usd",
            "turnaround_days",
            "included_revisions",
            "max_stems",
            "description",
        ]


class StudioRateSerializer(serializers.ModelSerializer):
    service_type_label = serializers.CharField(source="get_service_type_display", read_only=True)

    class Meta:
        model = StudioRate
        fields = ["service_type", "service_type_label", "hourly_price_usd"]
