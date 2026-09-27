from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, throttling, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from . import webhooks
from .models import Order
from .serializers import CheckoutResponseSerializer, CheckoutSerializer, OrderSerializer
from .services import CheckoutError, build_order, create_checkout_session


class CheckoutThrottle(throttling.UserRateThrottle):
    scope = "checkout"


class IsVerified(permissions.BasePermission):
    message = "Verify your email address before checking out."
    code = "email_unverified"

    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated
            and user.emailaddress_set.filter(email__iexact=user.email, verified=True).exists()
        )


@extend_schema(
    tags=["orders"],
    request=CheckoutSerializer,
    responses={200: CheckoutResponseSerializer},
    summary="Validate the cart, create a pending order and a Stripe Checkout session",
)
class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerified]
    throttle_classes = [CheckoutThrottle]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                order = build_order(
                    request.user,
                    serializer.validated_data["items"],
                    serializer.validated_data["locale"],
                )
                checkout_url = create_checkout_session(order)
        except CheckoutError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code, "line": exc.line},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"order_number": order.number, "checkout_url": checkout_url})


@extend_schema(tags=["orders"])
class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """The customer's own orders, newest first."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "number"
    lookup_value_regex = r"PS-\d{4}-\d{6}"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items__beat_license__beat", "items__service_product", "items__download_grants"
        )


@csrf_exempt
@require_POST
def stripe_webhook(request):
    signature = request.headers.get("Stripe-Signature", "")
    try:
        webhooks.process(request.body, signature)
    except webhooks.InvalidWebhook as exc:
        return HttpResponseBadRequest(str(exc))
    return HttpResponse(status=200)
