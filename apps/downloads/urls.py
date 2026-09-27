from django.urls import path

from .views import DownloadLinkView

urlpatterns = [
    path("downloads/<int:pk>/link", DownloadLinkView.as_view(), name="download-link"),
]
