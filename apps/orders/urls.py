from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CheckoutView, OrderViewSet, stripe_webhook

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("checkout", CheckoutView.as_view(), name="checkout"),
    path("stripe/webhook", stripe_webhook, name="stripe-webhook"),
    *router.urls,
]
