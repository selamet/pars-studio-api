from datetime import date

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import StudioRate

from . import rules, services
from .ics import build_ics
from .models import Reservation
from .serializers import (
    AvailabilitySerializer,
    BookingConfigSerializer,
    ReservationSerializer,
)


@extend_schema(
    tags=["bookings"], responses={200: BookingConfigSerializer}, summary="Scheduling rules"
)
class BookingConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Weekdays in JavaScript's getDay() convention (0 = Sunday) for the frontend calendar.
        closed_js = sorted((d + 1) % 7 for d in rules.CLOSED_WEEKDAYS)
        return Response(
            {
                "open_hour": rules.OPEN_HOUR,
                "close_hour": rules.CLOSE_HOUR,
                "closed_weekdays": closed_js,
                "max_advance_days": rules.MAX_ADVANCE_DAYS,
                "hold_minutes": settings.CHECKOUT_SESSION_TTL_MINUTES,
                "durations": {k: list(v) for k, v in rules.DURATIONS.items()},
                "service_types": [
                    {"id": value, "label": label} for value, label in StudioRate.ServiceType.choices
                ],
            }
        )


@extend_schema(
    tags=["bookings"],
    parameters=[
        OpenApiParameter("date", str, required=True, description="YYYY-MM-DD"),
        OpenApiParameter("service_type", str, required=True),
    ],
    responses={200: AvailabilitySerializer},
    summary="Free start hours for a day",
)
class AvailabilityView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            day = date.fromisoformat(request.query_params.get("date", ""))
        except ValueError:
            return Response(
                {"detail": "date must be YYYY-MM-DD.", "code": "invalid_date"}, status=400
            )
        service_type = request.query_params.get("service_type", "")
        if service_type not in rules.DURATIONS:
            return Response(
                {"detail": "Unknown service_type.", "code": "invalid_service"}, status=400
            )
        slots = services.availability(day, service_type)
        return Response(
            {
                "date": day,
                "service_type": service_type,
                "closed": services.is_closed(day),
                "slots": [{"start": f"{s.start:02d}:00", "durations": s.durations} for s in slots],
            }
        )


@extend_schema(tags=["bookings"])
class ReservationViewSet(viewsets.ReadOnlyModelViewSet):
    """The customer's own reservations."""

    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reservation.objects.filter(user=self.request.user).select_related(
            "order_item__order"
        )

    @extend_schema(responses={(200, "text/calendar"): str}, summary="Calendar file")
    @action(detail=True, methods=["get"])
    def ics(self, request, pk=None):
        reservation = self.get_object()
        response = HttpResponse(build_ics(reservation), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="pars-studio-{reservation.code}.ics"'
        )
        return response
