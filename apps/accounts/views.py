from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions

from .serializers import UserSerializer


@extend_schema(tags=["accounts"])
class MeView(generics.RetrieveUpdateAPIView):
    """The authenticated user's profile. Name fields are editable; email is managed by allauth."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user
