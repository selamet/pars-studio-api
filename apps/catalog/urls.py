from rest_framework.routers import DefaultRouter

from .views import BeatViewSet, ServiceProductViewSet, StudioRateViewSet

router = DefaultRouter()
router.register("beats", BeatViewSet, basename="beat")
router.register("services", ServiceProductViewSet, basename="service")
router.register("studio-rates", StudioRateViewSet, basename="studio-rate")

urlpatterns = router.urls
