from django.conf import settings
from django.core.files.storage import storages
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.storage import presigned_url
from apps.downloads.serializers import DownloadLinkSerializer

from . import uploads
from .models import InvalidTransition, ServiceFile, ServiceOrder
from .serializers import (
    ConfirmUploadSerializer,
    LocalUploadSerializer,
    MessageSerializer,
    PresignRequestSerializer,
    PresignResponseSerializer,
    ServiceFileSerializer,
    ServiceOrderSerializer,
)


def _error(code: str, detail: str, http_status=status.HTTP_409_CONFLICT):
    return Response({"detail": detail, "code": code}, status=http_status)


@extend_schema(tags=["services"])
class ServiceOrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """The customer's mastering/mixing jobs."""

    serializer_class = ServiceOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        return (
            ServiceOrder.objects.filter(user=self.request.user)
            .select_related("service_product", "order_item__order")
            .prefetch_related("files", "events__actor")
        )

    def perform_update(self, serializer):
        # Brief and links may be edited only until the studio starts working.
        if self.get_object().status not in (
            ServiceOrder.Status.AWAITING_FILES,
            ServiceOrder.Status.RECEIVED,
        ):
            raise exceptions.PermissionDenied(
                "The brief can only be edited before the studio starts working.",
                code="brief_locked",
            )
        serializer.save()

    @extend_schema(request=PresignRequestSerializer, responses={200: PresignResponseSerializer})
    @action(detail=True, methods=["post"], url_path="files/presign")
    def presign(self, request, pk=None):
        service_order = self.get_object()
        data = PresignRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = uploads.presign(
                service_order,
                data.validated_data["file_name"],
                data.validated_data["size"],
                data.validated_data["content_type"],
            )
        except uploads.UploadRejected as exc:
            return _error(exc.code, str(exc), status.HTTP_400_BAD_REQUEST)
        if not result.direct:
            result.upload_url = request.build_absolute_uri(
                f"/api/v1/service-orders/{service_order.pk}/files/upload/"
            )
        return Response(PresignResponseSerializer(result.__dict__).data)

    @extend_schema(request=LocalUploadSerializer, responses={201: ServiceFileSerializer})
    @action(detail=True, methods=["post"], url_path="files/upload")
    def upload(self, request, pk=None):
        """Local/dev fallback for environments without R2: the file body comes to Django."""
        service_order = self.get_object()
        data = LocalUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        key = data.validated_data["key"]
        try:
            uploads.validate(service_order, upload.name, upload.size)
        except uploads.UploadRejected as exc:
            return _error(exc.code, str(exc), status.HTTP_400_BAD_REQUEST)
        storages["private"].save(key, upload)
        return self._record_file(
            service_order, key, upload.name, upload.size, upload.content_type or ""
        )

    @extend_schema(request=ConfirmUploadSerializer, responses={201: ServiceFileSerializer})
    @action(detail=True, methods=["post"], url_path="files")
    def confirm(self, request, pk=None):
        """After a direct PUT to R2, register the object as a customer upload."""
        service_order = self.get_object()
        data = ConfirmUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        try:
            uploads.validate(service_order, v["file_name"], v["size"])
        except uploads.UploadRejected as exc:
            return _error(exc.code, str(exc), status.HTTP_400_BAD_REQUEST)
        if not v["key"].startswith(f"services/{service_order.pk}/customer_upload/"):
            return _error(
                "bad_key", "Key does not belong to this order.", status.HTTP_400_BAD_REQUEST
            )
        if not uploads.object_exists(v["key"], v["size"]):
            return _error(
                "not_uploaded", "The file was not found in storage.", status.HTTP_400_BAD_REQUEST
            )
        return self._record_file(
            service_order, v["key"], v["file_name"], v["size"], v["content_type"]
        )

    def _record_file(self, service_order, key, name, size, content_type):
        with transaction.atomic():
            service_file = ServiceFile.objects.create(
                service_order=service_order,
                direction=ServiceFile.Direction.CUSTOMER_UPLOAD,
                file=key,
                original_name=uploads.clean_name(name),
                size=size,
                content_type=content_type,
                uploaded_by=self.request.user,
                round=service_order.revisions_used,
            )
            if service_order.status == ServiceOrder.Status.AWAITING_FILES:
                service_order.transition(
                    ServiceOrder.Status.RECEIVED, actor="customer", by=self.request.user
                )
        return Response(ServiceFileSerializer(service_file).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=MessageSerializer, responses={200: ServiceOrderSerializer})
    @action(detail=True, methods=["post"], url_path="request-revision")
    def request_revision(self, request, pk=None):
        service_order = self.get_object()
        data = MessageSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if service_order.revisions_left <= 0:
            return _error("no_revisions_left", "All included revisions have been used.")
        if not data.validated_data["message"].strip():
            return _error(
                "message_required", "Tell the studio what to change.", status.HTTP_400_BAD_REQUEST
            )
        try:
            service_order.transition(
                ServiceOrder.Status.REVISION_REQUESTED,
                actor="customer",
                by=request.user,
                message=data.validated_data["message"],
            )
        except InvalidTransition as exc:
            return _error("invalid_transition", str(exc))
        return Response(self.get_serializer(service_order).data)

    @extend_schema(request=None, responses={200: ServiceOrderSerializer})
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        service_order = self.get_object()
        try:
            service_order.transition(
                ServiceOrder.Status.COMPLETED, actor="customer", by=request.user
            )
        except InvalidTransition as exc:
            return _error("invalid_transition", str(exc))
        return Response(self.get_serializer(service_order).data)

    @extend_schema(request=None, responses={200: DownloadLinkSerializer})
    @action(detail=True, methods=["post"], url_path=r"files/(?P<file_id>\d+)/link")
    def link(self, request, pk=None, file_id=None):
        service_order = self.get_object()
        service_file = service_order.files.filter(pk=file_id).first()
        if service_file is None:
            return _error("not_found", "File not found.", status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "url": presigned_url(service_file.file),
                "expires_in": settings.PRESIGNED_URL_TTL,
                "file_name": service_file.original_name,
            }
        )
