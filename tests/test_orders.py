import json
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from stripe import WebhookSignature

from apps.catalog.models import Beat, BeatLicense, ServiceProduct
from apps.downloads.models import DownloadGrant
from apps.orders.models import Order, Payment
from apps.orders.services import expire_pending_orders


@pytest.fixture
def catalog(db):
    beat = Beat.objects.create(title="Night Drive", bpm=92, status=Beat.Status.PUBLISHED)
    mp3 = BeatLicense.objects.create(
        beat=beat,
        tier="mp3_lease",
        price_usd="29.00",
        mp3_file=SimpleUploadedFile("night-drive.mp3", b"id3"),
    )
    wav = BeatLicense.objects.create(
        beat=beat,
        tier="wav_lease",
        price_usd="49.00",
        mp3_file=SimpleUploadedFile("night-drive.mp3", b"id3"),
        wav_file=SimpleUploadedFile("night-drive.wav", b"RIFF"),
    )
    exclusive = BeatLicense.objects.create(beat=beat, tier="exclusive", price_usd="499.00")
    service = ServiceProduct.objects.create(
        name="Single Mastering", kind="mastering", price_usd="60.00"
    )
    return SimpleNamespace(beat=beat, mp3=mp3, wav=wav, exclusive=exclusive, service=service)


@pytest.fixture
def stripe_session():
    """Patch Stripe's Checkout Session creation; yields the mock so tests can inspect calls."""
    with mock.patch("stripe.checkout.Session.create") as create:
        create.return_value = SimpleNamespace(
            id="cs_test_123", url="https://checkout.stripe.com/c/cs_test_123"
        )
        yield create


def signed(payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    ts = int(time.time())
    sig = WebhookSignature._compute_signature(
        f"{ts}.{body.decode()}", settings.STRIPE_WEBHOOK_SECRET
    )
    return body, f"t={ts},v1={sig}"


def completed_event(order: Order, event_id="evt_1", paid=True, amount=None):
    return {
        "id": event_id,
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": order.stripe_checkout_session_id or "cs_test_123",
                "object": "checkout.session",
                "payment_status": "paid" if paid else "unpaid",
                "payment_intent": "pi_test_1",
                "amount_total": int((amount or order.total) * 100),
                "currency": order.currency.lower(),
                "metadata": {"order_id": str(order.pk), "order_number": order.number},
            }
        },
    }


def post_webhook(client, payload):
    body, header = signed(payload)
    return client.post(
        "/api/v1/stripe/webhook",
        body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )


# --- checkout -----------------------------------------------------------------


@pytest.mark.django_db
def test_checkout_requires_verified_email(api_client, user, catalog):
    api_client.force_authenticate(user)
    response = api_client.post(
        "/api/v1/checkout",
        {"items": [{"type": "beat_license", "id": catalog.mp3.pk}]},
        format="json",
    )
    assert response.status_code == 403
    assert response.json()["code"] == "email_unverified"


@pytest.mark.django_db
def test_checkout_creates_pending_order_with_db_prices(
    api_client, verified_user, catalog, stripe_session
):
    api_client.force_authenticate(verified_user)
    response = api_client.post(
        "/api/v1/checkout",
        {
            "items": [
                {"type": "beat_license", "id": catalog.wav.pk, "price": "0.01"},
                {"type": "service", "id": catalog.service.pk},
            ],
            "locale": "tr",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["checkout_url"].startswith("https://checkout.stripe.com/")

    order = Order.objects.get(number=data["order_number"])
    assert order.status == Order.Status.PENDING
    assert order.total == Decimal("109.00")
    assert order.stripe_checkout_session_id == "cs_test_123"
    assert order.expires_at is not None
    assert [i.title for i in order.items.all()] == ["Night Drive — WAV Lease", "Single Mastering"]

    kwargs = stripe_session.call_args.kwargs
    assert kwargs["client_reference_id"] == order.number
    assert [li["price_data"]["unit_amount"] for li in kwargs["line_items"]] == [4900, 6000]
    assert kwargs["success_url"].endswith(f"/tr/checkout/success?order={order.number}")


@pytest.mark.django_db
def test_checkout_rejects_unavailable_items(api_client, verified_user, catalog, stripe_session):
    api_client.force_authenticate(verified_user)
    catalog.mp3.is_active = False
    catalog.mp3.save()
    response = api_client.post(
        "/api/v1/checkout",
        {"items": [{"type": "beat_license", "id": catalog.mp3.pk}]},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "unavailable"
    assert response.json()["line"] == {"type": "beat_license", "id": catalog.mp3.pk}
    assert Order.objects.count() == 0
    stripe_session.assert_not_called()


@pytest.mark.django_db
def test_checkout_rejects_lease_plus_exclusive_of_same_beat(
    api_client, verified_user, catalog, stripe_session
):
    api_client.force_authenticate(verified_user)
    response = api_client.post(
        "/api/v1/checkout",
        {
            "items": [
                {"type": "beat_license", "id": catalog.mp3.pk},
                {"type": "beat_license", "id": catalog.exclusive.pk},
            ]
        },
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "invalid"


# --- webhooks -----------------------------------------------------------------


@pytest.mark.django_db
def test_webhook_rejects_bad_signature(client, verified_user, catalog):
    response = client.post(
        "/api/v1/stripe/webhook",
        b"{}",
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="t=1,v1=bad",
    )
    assert response.status_code == 400
    assert Payment.objects.count() == 0


@pytest.fixture
def pending_order(api_client, verified_user, catalog, stripe_session):
    api_client.force_authenticate(verified_user)
    response = api_client.post(
        "/api/v1/checkout",
        {
            "items": [
                {"type": "beat_license", "id": catalog.wav.pk},
                {"type": "service", "id": catalog.service.pk},
            ]
        },
        format="json",
    )
    return Order.objects.get(number=response.json()["order_number"])


@pytest.mark.django_db
def test_completed_session_marks_paid_fulfils_and_emails(
    client, pending_order, verified_user, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = post_webhook(client, completed_event(pending_order))
    assert response.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.PAID
    assert pending_order.paid_at is not None
    assert pending_order.stripe_payment_intent_id == "pi_test_1"
    assert pending_order.fulfilled_at is not None
    assert pending_order.fulfilment_notes == ""

    grants = DownloadGrant.objects.filter(user=verified_user).order_by("file_kind")
    assert [g.file_kind for g in grants] == ["mp3", "wav"]
    assert all(g.is_available for g in grants)

    payment = Payment.objects.get(provider_event_id="evt_1")
    assert payment.type == Payment.Type.CHECKOUT_COMPLETED
    assert payment.amount == Decimal("109.00")

    assert sorted(m.to[0] for m in mail.outbox) == sorted(
        [verified_user.email, settings.STUDIO_NOTIFICATION_EMAIL]
    )
    assert pending_order.number in mail.outbox[0].subject


@pytest.mark.django_db
@pytest.mark.parametrize(
    "override",
    [{"amount_total": 100}, {"currency": "eur"}],
    ids=["amount", "currency"],
)
def test_completed_session_with_mismatched_total_stays_pending(
    client, pending_order, override, django_capture_on_commit_callbacks
):
    event = completed_event(pending_order)
    event["data"]["object"].update(override)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_webhook(client, event)
    assert response.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.PENDING
    assert pending_order.paid_at is None
    assert not DownloadGrant.objects.exists()
    assert mail.outbox == []

    payment = Payment.objects.get(provider_event_id="evt_1")
    assert payment.order == pending_order
    assert payment.type == Payment.Type.AMOUNT_MISMATCH


@pytest.mark.django_db
def test_webhook_replay_is_idempotent(client, pending_order, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, completed_event(pending_order))
        response = post_webhook(client, completed_event(pending_order))
    assert response.status_code == 200
    assert Payment.objects.count() == 1
    assert DownloadGrant.objects.count() == 2
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_expired_session_cancels_order(client, pending_order):
    event = completed_event(pending_order, event_id="evt_exp")
    event["type"] = "checkout.session.expired"
    assert post_webhook(client, event).status_code == 200
    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.CANCELLED


@pytest.mark.django_db
def test_exclusive_purchase_closes_the_beat(
    api_client, client, verified_user, catalog, stripe_session, django_capture_on_commit_callbacks
):
    api_client.force_authenticate(verified_user)
    response = api_client.post(
        "/api/v1/checkout",
        {"items": [{"type": "beat_license", "id": catalog.exclusive.pk}]},
        format="json",
    )
    order = Order.objects.get(number=response.json()["order_number"])
    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, completed_event(order, event_id="evt_excl"))

    catalog.beat.refresh_from_db()
    assert catalog.beat.status == Beat.Status.SOLD_EXCLUSIVE
    assert not catalog.beat.licenses.filter(is_active=True).exists()

    # Nobody can buy anything on this beat any more.
    response = api_client.post(
        "/api/v1/checkout",
        {"items": [{"type": "beat_license", "id": catalog.mp3.pk}]},
        format="json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_refund_revokes_downloads(client, pending_order, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, completed_event(pending_order))
    refund = {
        "id": "evt_refund",
        "object": "event",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_1",
                "object": "charge",
                "payment_intent": "pi_test_1",
                "refunded": True,
                "amount_refunded": 10900,
            }
        },
    }
    assert post_webhook(client, refund).status_code == 200
    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.REFUNDED
    assert not DownloadGrant.objects.filter(revoked=False).exists()


# --- customer API -------------------------------------------------------------


@pytest.mark.django_db
def test_orders_are_private_and_include_downloads(
    api_client,
    client,
    pending_order,
    verified_user,
    django_user_model,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, completed_event(pending_order))

    api_client.force_authenticate(verified_user)
    response = api_client.get("/api/v1/orders/")
    assert response.status_code == 200
    orders = response.json()["results"]
    assert [o["number"] for o in orders] == [pending_order.number]
    assert orders[0]["status"] == "paid"
    beat_item = next(i for i in orders[0]["items"] if i["item_type"] == "beat_license")
    assert beat_item["beat_slug"] == "night-drive"
    assert [d["file_kind"] for d in beat_item["downloads"]] == ["mp3", "wav"]

    stranger = django_user_model.objects.create_user(email="x@example.com", password="pw-123456")
    api_client.force_authenticate(stranger)
    assert api_client.get(f"/api/v1/orders/{pending_order.number}/").status_code == 404


@pytest.mark.django_db
def test_download_link_counts_and_expires(
    api_client,
    client,
    pending_order,
    verified_user,
    django_user_model,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, completed_event(pending_order))
    grant = DownloadGrant.objects.get(file_kind="wav")

    api_client.force_authenticate(verified_user)
    response = api_client.post(f"/api/v1/downloads/{grant.pk}/link")
    assert response.status_code == 200, response.content
    assert response.json()["file_name"].endswith(".wav")
    assert response.json()["url"]
    grant.refresh_from_db()
    assert grant.download_count == 1

    grant.download_count = grant.max_downloads
    grant.save()
    assert api_client.post(f"/api/v1/downloads/{grant.pk}/link").status_code == 410

    grant.download_count = 0
    grant.expires_at = timezone.now() - timezone.timedelta(days=1)
    grant.save()
    assert api_client.post(f"/api/v1/downloads/{grant.pk}/link").status_code == 410

    stranger = django_user_model.objects.create_user(email="x@example.com", password="pw-123456")
    api_client.force_authenticate(stranger)
    assert api_client.post(f"/api/v1/downloads/{grant.pk}/link").status_code == 404


@pytest.mark.django_db
def test_expire_pending_orders(pending_order):
    pending_order.expires_at = timezone.now() - timezone.timedelta(minutes=1)
    pending_order.save()
    assert expire_pending_orders() == 1
    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.CANCELLED


@pytest.mark.django_db
def test_order_admin_pages_render(admin_client, pending_order):
    for url in [
        "/admin/orders/order/",
        f"/admin/orders/order/{pending_order.pk}/change/",
        "/admin/orders/payment/",
        "/admin/downloads/downloadgrant/",
    ]:
        assert admin_client.get(url).status_code == 200, url


@pytest.mark.django_db
def test_checkout_reports_stripe_outage_and_keeps_no_order(api_client, verified_user, catalog):
    import stripe

    api_client.force_authenticate(verified_user)
    with mock.patch(
        "stripe.checkout.Session.create", side_effect=stripe.APIConnectionError("down")
    ):
        response = api_client.post(
            "/api/v1/checkout",
            {"items": [{"type": "service", "id": catalog.service.pk}]},
            format="json",
        )
    assert response.status_code == 502
    assert response.json()["code"] == "payment_unavailable"
    assert Order.objects.count() == 0
