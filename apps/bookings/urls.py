from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AvailabilityView, BookingConfigView, ReservationViewSet

router = DefaultRouter()
router.register("", ReservationViewSet, basename="reservation")

urlpatterns = [
    path("config", BookingConfigView.as_view(), name="booking-config"),
    path("availability", AvailabilityView.as_view(), name="booking-availability"),
    *router.urls,
]
