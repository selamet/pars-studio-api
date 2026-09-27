from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.storage import presigned_url

from .models import DownloadGrant
from .serializers import DownloadLinkSerializer


@extend_schema(
    tags=["orders"],
    responses={200: DownloadLinkSerializer},
    summary="Mint a short-lived download URL for a purchased file",
)
class DownloadLinkView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        with transaction.atomic():
            grant = (
                DownloadGrant.objects.select_for_update(of=("self",))
                .select_related("order_item__beat_license")
                .filter(pk=pk, user=request.user)
                .first()
            )
            if grant is None:
                return Response({"detail": "Not found.", "code": "not_found"}, status=404)
            if not grant.is_available:
                return Response(
                    {
                        "detail": "This download is no longer available.",
                        "code": "download_unavailable",
                    },
                    status=status.HTTP_410_GONE,
                )
            file = grant.file
            if not file:
                return Response(
                    {
                        "detail": "The file is not ready yet. The studio has been notified.",
                        "code": "file_missing",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            grant.download_count += 1
            grant.last_downloaded_at = timezone.now()
            grant.save(update_fields=["download_count", "last_downloaded_at", "updated_at"])
        url = presigned_url(file)
        return Response(
            {
                "url": url,
                "expires_in": settings.PRESIGNED_URL_TTL,
                "file_name": file.name.rsplit("/", 1)[-1],
            }
        )
