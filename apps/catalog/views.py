from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, viewsets

from .filters import BeatFilter
from .models import Beat, BeatLicense, ServiceProduct, StudioRate
from .serializers import (
    BeatDetailSerializer,
    BeatListSerializer,
    ServiceProductSerializer,
    StudioRateSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["catalog"], summary="Published beats"),
    retrieve=extend_schema(tags=["catalog"], summary="Beat with purchasable licenses"),
)
class BeatViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    filterset_class = BeatFilter
    search_fields = ["title", "genre", "tags"]
    ordering_fields = ["published_at", "bpm", "title"]
    ordering = ["-published_at"]

    def get_queryset(self):
        return Beat.objects.published().prefetch_related(
            Prefetch("licenses", queryset=BeatLicense.objects.filter(is_active=True))
        )

    def get_serializer_class(self):
        return BeatDetailSerializer if self.action == "retrieve" else BeatListSerializer


@extend_schema_view(
    list=extend_schema(tags=["catalog"], summary="Active mastering / mixing products"),
    retrieve=extend_schema(tags=["catalog"]),
)
class ServiceProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    serializer_class = ServiceProductSerializer
    queryset = ServiceProduct.objects.filter(is_active=True)
    filterset_fields = ["kind"]
    pagination_class = None


@extend_schema_view(list=extend_schema(tags=["catalog"], summary="Hourly studio rates"))
class StudioRateViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "service_type"
    serializer_class = StudioRateSerializer
    queryset = StudioRate.objects.filter(is_active=True)
    pagination_class = None
