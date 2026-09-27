from types import SimpleNamespace
from unittest import mock

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import ServiceProduct
from apps.orders.fulfilment import fulfil_order
from apps.orders.models import Order, OrderItem
from apps.services.models import ServiceFile, ServiceOrder


@pytest.fixture
def paid_service_order(db, verified_user):
    product = ServiceProduct.objects.create(
        name="Single Mastering",
        kind="mastering",
        price_usd="60.00",
        turnaround_days=3,
        included_revisions=1,
        max_stems=2,
    )
    order = Order.objects.create(
        user=verified_user, customer_email=verified_user.email, status=Order.Status.PAID
    )
    OrderItem.objects.create(
        order=order,
        item_type=OrderItem.ItemType.SERVICE,
        service_product=product,
        title=product.name,
        unit_price=product.price_usd,
    )
    order.recalculate()
    fulfil_order(order)
    mail.outbox.clear()
    return ServiceOrder.objects.get(order_item__order=order)


def upload(api_client, service_order, name="mix.wav", size=None, content=b"RIFF" * 100):
    """Drive the local (non-R2) flow: presign → upload endpoint."""
    size = size or len(content)
    presign = api_client.post(
        f"/api/v1/service-orders/{service_order.pk}/files/presign/",
        {"file_name": name, "size": size, "content_type": "audio/wav"},
        format="json",
    )
    if presign.status_code != 200:
        return presign
    assert presign.json()["direct"] is False
    return api_client.post(
        presign.json()["upload_url"],
        {"key": presign.json()["key"], "file": SimpleUploadedFile(name, content)},
        format="multipart",
    )


@pytest.mark.django_db
def test_fulfilment_creates_service_order_with_due_date(paid_service_order):
    assert paid_service_order.status == ServiceOrder.Status.AWAITING_FILES
    assert paid_service_order.due_at is not None
    assert paid_service_order.revisions_left == 1


@pytest.mark.django_db
def test_customer_upload_moves_to_received_and_notifies_studio(
    api_client, verified_user, paid_service_order
):
    api_client.force_authenticate(verified_user)
    response = upload(api_client, paid_service_order)
    assert response.status_code == 201, response.content
    assert response.json()["direction"] == "customer_upload"

    paid_service_order.refresh_from_db()
    assert paid_service_order.status == ServiceOrder.Status.RECEIVED
    assert paid_service_order.files.count() == 1
    assert paid_service_order.events.count() == 1
    assert [m.to[0] for m in mail.outbox] == [settings.STUDIO_NOTIFICATION_EMAIL]

    detail = api_client.get(f"/api/v1/service-orders/{paid_service_order.pk}/").json()
    assert detail["status"] == "received"
    assert detail["files"][0]["original_name"] == "mix.wav"
    assert detail["events"][0]["to_status"] == "received"


@pytest.mark.django_db
def test_upload_validation(api_client, verified_user, paid_service_order):
    api_client.force_authenticate(verified_user)
    bad_ext = api_client.post(
        f"/api/v1/service-orders/{paid_service_order.pk}/files/presign/",
        {"file_name": "notes.txt", "size": 10},
        format="json",
    )
    assert bad_ext.status_code == 400 and bad_ext.json()["code"] == "bad_extension"

    too_big = api_client.post(
        f"/api/v1/service-orders/{paid_service_order.pk}/files/presign/",
        {"file_name": "big.wav", "size": settings.SERVICE_UPLOAD_MAX_MB * 1024 * 1024 + 1},
        format="json",
    )
    assert too_big.status_code == 400 and too_big.json()["code"] == "too_large"

    assert upload(api_client, paid_service_order, "a.wav").status_code == 201
    assert upload(api_client, paid_service_order, "b.wav").status_code == 201
    third = upload(api_client, paid_service_order, "c.wav")
    assert third.status_code == 400 and third.json()["code"] == "too_many_files"


@pytest.mark.django_db
def test_other_users_cannot_see_or_upload(api_client, paid_service_order, django_user_model):
    stranger = django_user_model.objects.create_user(email="x@example.com", password="pw-123456")
    api_client.force_authenticate(stranger)
    assert api_client.get(f"/api/v1/service-orders/{paid_service_order.pk}/").status_code == 404
    assert upload(api_client, paid_service_order).status_code == 404
    assert api_client.get("/api/v1/service-orders/").json()["count"] == 0


@pytest.mark.django_db
def test_studio_workflow_delivery_revision_and_accept(
    api_client, admin_user, verified_user, paid_service_order
):
    api_client.force_authenticate(verified_user)
    upload(api_client, paid_service_order)
    paid_service_order.refresh_from_db()
    mail.outbox.clear()

    # Studio works and delivers (as the admin actions do).
    paid_service_order.transition(ServiceOrder.Status.IN_PROGRESS, actor="studio", by=admin_user)
    ServiceFile.objects.create(
        service_order=paid_service_order,
        direction=ServiceFile.Direction.STUDIO_DELIVERABLE,
        file=SimpleUploadedFile("master.wav", b"RIFF"),
        original_name="master.wav",
        size=4,
        uploaded_by=admin_user,
    )
    paid_service_order.transition(
        ServiceOrder.Status.DELIVERED, actor="studio", by=admin_user, message="Enjoy!"
    )
    assert [m.to[0] for m in mail.outbox] == [verified_user.email, verified_user.email]
    assert "Enjoy!" in mail.outbox[-1].body

    # Customer downloads the deliverable.
    deliverable = paid_service_order.files.get(direction="studio_deliverable")
    link = api_client.post(
        f"/api/v1/service-orders/{paid_service_order.pk}/files/{deliverable.pk}/link/"
    )
    assert link.status_code == 200 and link.json()["file_name"] == "master.wav"

    # Revision without a message is refused; with one it flips the status and re-opens uploads.
    no_msg = api_client.post(
        f"/api/v1/service-orders/{paid_service_order.pk}/request-revision/", {}, format="json"
    )
    assert no_msg.status_code == 400
    revision = api_client.post(
        f"/api/v1/service-orders/{paid_service_order.pk}/request-revision/",
        {"message": "Vocals louder please"},
        format="json",
    )
    assert revision.status_code == 200
    assert revision.json()["status"] == "revision_requested"
    assert revision.json()["revisions_left"] == 0
    assert revision.json()["accepts_uploads"] is True
    assert upload(api_client, paid_service_order, "ref.wav").status_code == 201

    paid_service_order.refresh_from_db()
    paid_service_order.transition(ServiceOrder.Status.DELIVERED, actor="studio", by=admin_user)
    again = api_client.post(
        f"/api/v1/service-orders/{paid_service_order.pk}/request-revision/",
        {"message": "one more"},
        format="json",
    )
    assert again.status_code == 409 and again.json()["code"] == "no_revisions_left"

    accepted = api_client.post(f"/api/v1/service-orders/{paid_service_order.pk}/accept/")
    assert accepted.status_code == 200 and accepted.json()["status"] == "completed"
    repeat = api_client.post(f"/api/v1/service-orders/{paid_service_order.pk}/accept/")
    assert repeat.status_code == 409


@pytest.mark.django_db
def test_brief_is_editable_only_before_work_starts(
    api_client, admin_user, verified_user, paid_service_order
):
    api_client.force_authenticate(verified_user)
    ok = api_client.patch(
        f"/api/v1/service-orders/{paid_service_order.pk}/",
        {"notes": "Loud but clean"},
        format="json",
    )
    assert ok.status_code == 200 and ok.json()["notes"] == "Loud but clean"
    upload(api_client, paid_service_order)
    paid_service_order.refresh_from_db()
    paid_service_order.transition(ServiceOrder.Status.IN_PROGRESS, actor="studio", by=admin_user)
    locked = api_client.patch(
        f"/api/v1/service-orders/{paid_service_order.pk}/",
        {"notes": "changed my mind"},
        format="json",
    )
    assert locked.status_code == 403 and locked.json()["code"] == "brief_locked"


@pytest.mark.django_db
def test_presign_uses_r2_when_configured(api_client, verified_user, paid_service_order):
    api_client.force_authenticate(verified_user)
    fake_storage = SimpleNamespace(
        bucket=object(),
        bucket_name="pars-private",
        connection=SimpleNamespace(
            meta=SimpleNamespace(
                client=SimpleNamespace(
                    generate_presigned_url=lambda *a, **k: "https://r2.example/put"
                )
            )
        ),
    )
    with mock.patch("apps.services.uploads.storages", {"private": fake_storage}):
        response = api_client.post(
            f"/api/v1/service-orders/{paid_service_order.pk}/files/presign/",
            {"file_name": "mix.wav", "size": 1000, "content_type": "audio/wav"},
            format="json",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["direct"] is True and body["method"] == "PUT"
    assert body["upload_url"] == "https://r2.example/put"
    assert body["key"].startswith(f"services/{paid_service_order.pk}/customer_upload/")


@pytest.mark.django_db
def test_service_admin_pages_and_actions(
    admin_client, admin_user, verified_user, paid_service_order
):
    for url in [
        "/admin/services/serviceorder/",
        f"/admin/services/serviceorder/{paid_service_order.pk}/change/",
    ]:
        assert admin_client.get(url).status_code == 200, url
    # Deliver without a deliverable is refused; start_work from awaiting_files is invalid too.
    admin_client.post(
        "/admin/services/serviceorder/",
        {"action": "deliver", "_selected_action": [paid_service_order.pk]},
        follow=True,
    )
    paid_service_order.refresh_from_db()
    assert paid_service_order.status == ServiceOrder.Status.AWAITING_FILES
