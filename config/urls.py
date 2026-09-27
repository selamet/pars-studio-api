from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    # allauth: provider callbacks live under /accounts/, the headless JSON API under /_allauth/.
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
    # Project API
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/catalog/", include("apps.catalog.urls")),
    path("api/v1/", include("apps.orders.urls")),
    path("api/v1/", include("apps.downloads.urls")),
    path("api/v1/", include("apps.services.urls")),
    path("api/v1/bookings/", include("apps.bookings.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
