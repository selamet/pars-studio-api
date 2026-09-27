from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.conf import settings
from django.core import mail
from django.utils import timezone

from apps.bookings import services as booking_services
from apps.bookings.models import Reservation
from apps.catalog.models import StudioRate
from apps.orders.models import Order

from .test_orders import completed_event, post_webhook


def next_open_day(days_ahead: int = 7) -> date:
    day = timezone.localdate() + timedelta(days=days_ahead)
    while day.weekday() == 6:  # Sunday
        day += timedelta(days=1)
    return day


@pytest.fixture
def rates(db):
    StudioRate.objects.create(service_type="recording", hourly_price_usd=Decimal("45.00"))
    StudioRate.objects.create(service_type="mastering", hourly_price_usd=Decimal("50.00"))


@pytest.fixture
def stripe_session():
    with mock.patch("stripe.checkout.Session.create") as create:
        create.return_value = SimpleNamespace(
            id="cs_test_b", url="https://checkout.stripe.com/c/cs_test_b"
        )
        yield create


def booking_line(day: date, start="14:00", duration=2, service="recording", **extra):
    return {
        "type": "booking",
        "booking": {
            "service_type": service,
            "session_date": day.isoformat(),
            "start_time": start,
            "duration_hours": duration,
            "customer_name": "Ada Lovelace",
            "customer_phone": "+905551112233",
            **extra,
        },
    }


@pytest.mark.django_db
def test_config_and_availability_follow_the_rules(api_client, rates):
    config = api_client.get("/api/v1/bookings/config").json()
    assert config["open_hour"] == 10 and config["close_hour"] == 22
    assert config["closed_weekdays"] == [0]  # Sunday in JS convention
    assert config["durations"]["mastering"] == [1, 2]

    day = next_open_day()
    response = api_client.get(f"/api/v1/bookings/availability?date={day}&service_type=recording")
    assert response.status_code == 200
    slots = response.json()["slots"]
    assert slots[0] == {"start": "10:00", "durations": [2, 4, 8]}
    assert slots[-1] == {"start": "20:00", "durations": [2]}  # 21:00 cannot fit 2 h before 22:00

    sunday = day + timedelta(days=(6 - day.weekday()) % 7 or 7)
    closed = api_client.get(
        f"/api/v1/bookings/availability?date={sunday}&service_type=recording"
    ).json()
    assert closed["closed"] is True and closed["slots"] == []

    assert (
        api_client.get("/api/v1/bookings/availability?date=nope&service_type=recording").status_code
        == 400
    )
    assert (
        api_client.get(f"/api/v1/bookings/availability?date={day}&service_type=dj").status_code
        == 400
    )


@pytest.mark.django_db
def test_checkout_holds_the_slot_and_prices_from_rates(
    api_client, verified_user, rates, stripe_session
):
    api_client.force_authenticate(verified_user)
    day = next_open_day()
    response = api_client.post(
        "/api/v1/checkout",
        {"items": [booking_line(day, "14:00", 4)], "locale": "tr"},
        format="json",
    )
    assert response.status_code == 200, response.content
    order = Order.objects.get(number=response.json()["order_number"])
    assert order.total == Decimal("180.00")
    item = order.items.get()
    assert item.item_type == "booking"
    reservation = item.reservation
    assert reservation.status == Reservation.Status.HOLD
    assert reservation.hold_expires_at is not None
    assert reservation.user == verified_user
    assert reservation.customer_email == verified_user.email
    assert (reservation.slot.lower, reservation.slot.upper) == (14, 18)

    # The held hours disappear from availability for everyone.
    slots = api_client.get(
        f"/api/v1/bookings/availability?date={day}&service_type=recording"
    ).json()["slots"]
    starts = [s["start"] for s in slots]
    assert "14:00" not in starts and "16:00" not in starts
    assert next(s for s in slots if s["start"] == "12:00")["durations"] == [2]


@pytest.mark.django_db
def test_double_booking_is_refused_by_the_database(
    api_client, verified_user, rates, stripe_session, django_user_model
):
    day = next_open_day()
    api_client.force_authenticate(verified_user)
    first = api_client.post(
        "/api/v1/checkout", {"items": [booking_line(day, "14:00", 2)]}, format="json"
    )
    assert first.status_code == 200

    other = django_user_model.objects.create_user(email="other@example.com", password="pw-123456")
    from allauth.account.models import EmailAddress

    EmailAddress.objects.create(user=other, email=other.email, verified=True, primary=True)
    api_client.force_authenticate(other)
    second = api_client.post(
        "/api/v1/checkout", {"items": [booking_line(day, "15:00", 2)]}, format="json"
    )
    assert second.status_code == 409
    assert second.json()["code"] == "slot_taken"
    assert second.json()["line"]["start_time"] == "15:00"
    assert Order.objects.filter(user=other).count() == 0
    assert Reservation.objects.count() == 1


@pytest.mark.django_db
def test_rule_violations(api_client, verified_user, rates, stripe_session):
    api_client.force_authenticate(verified_user)
    day = next_open_day()

    def attempt(**kwargs):
        line = booking_line(day, **kwargs)
        return api_client.post("/api/v1/checkout", {"items": [line]}, format="json")

    assert attempt(start="21:00", duration=2).json()["code"] == "outside_hours"
    assert attempt(duration=1).json()["code"] == "invalid_duration"  # recording min 2 h
    assert attempt(start="14:30").status_code == 409
    past = api_client.post(
        "/api/v1/checkout",
        {"items": [booking_line(timezone.localdate() - timedelta(days=1))]},
        format="json",
    )
    assert past.json()["code"] == "past_date"
    unrated = api_client.post(
        "/api/v1/checkout",
        {"items": [booking_line(day, service="vocal", duration=2)]},
        format="json",
    )
    assert unrated.json()["code"] == "no_rate"


@pytest.mark.django_db
def test_payment_confirms_and_emails_with_ics(
    api_client, client, verified_user, rates, stripe_session, django_capture_on_commit_callbacks
):
    api_client.force_authenticate(verified_user)
    day = next_open_day()
    response = api_client.post(
        "/api/v1/checkout", {"items": [booking_line(day, "10:00", 2)]}, format="json"
    )
    order = Order.objects.get(number=response.json()["order_number"])
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, completed_event(order, event_id="evt_booking"))

    reservation = Reservation.objects.get()
    assert reservation.status == Reservation.Status.CONFIRMED
    assert reservation.hold_expires_at is None
    recipients = sorted(m.to[0] for m in mail.outbox)
    assert recipients == sorted(
        [
            verified_user.email,
            verified_user.email,
            settings.STUDIO_NOTIFICATION_EMAIL,
            settings.STUDIO_NOTIFICATION_EMAIL,
        ]
    )
    confirmation = next(m for m in mail.outbox if "confirmed" in m.subject.lower())
    assert confirmation.attachments[0][0] == f"pars-studio-{reservation.code}.ics"
    assert "BEGIN:VCALENDAR" in confirmation.attachments[0][1]

    # Customer API + ICS endpoint are owner-only.
    listing = api_client.get("/api/v1/bookings/").json()["results"]
    assert listing[0]["status"] == "confirmed" and listing[0]["order_number"] == order.number
    ics = api_client.get(f"/api/v1/bookings/{reservation.pk}/ics/")
    assert ics.status_code == 200 and ics["Content-Type"].startswith("text/calendar")
    api_client.force_authenticate(None)
    assert api_client.get(f"/api/v1/bookings/{reservation.pk}/ics/").status_code == 403


@pytest.mark.django_db
def test_expired_checkout_releases_the_hold(
    api_client, client, verified_user, rates, stripe_session
):
    api_client.force_authenticate(verified_user)
    day = next_open_day()
    response = api_client.post(
        "/api/v1/checkout", {"items": [booking_line(day, "12:00", 2)]}, format="json"
    )
    order = Order.objects.get(number=response.json()["order_number"])
    event = completed_event(order, event_id="evt_exp_b")
    event["type"] = "checkout.session.expired"
    post_webhook(client, event)
    reservation = Reservation.objects.get()
    assert reservation.status == Reservation.Status.EXPIRED
    starts = [
        s["start"]
        for s in api_client.get(
            f"/api/v1/bookings/availability?date={day}&service_type=recording"
        ).json()["slots"]
    ]
    assert "12:00" in starts


@pytest.mark.django_db
def test_expire_holds_command_and_stale_orders(api_client, verified_user, rates, stripe_session):
    api_client.force_authenticate(verified_user)
    day = next_open_day()
    api_client.post("/api/v1/checkout", {"items": [booking_line(day, "16:00", 2)]}, format="json")
    Reservation.objects.update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    assert booking_services.expire_holds() == 1
    assert Reservation.objects.get().status == Reservation.Status.EXPIRED


@pytest.mark.django_db
def test_admin_pages_and_confirm_action(admin_client, verified_user, rates):
    day = next_open_day()
    reservation = booking_services.create_hold(
        verified_user,
        {
            "service_type": "mastering",
            "session_date": day,
            "start_time": time(11, 0),
            "duration_hours": 1,
            "customer_name": "Ada",
            "customer_phone": "+90555",
        },
        hold_until=timezone.now() + timedelta(minutes=30),
        locale="en",
    )
    assert admin_client.get("/admin/bookings/reservation/").status_code == 200
    assert (
        admin_client.get(f"/admin/bookings/reservation/{reservation.pk}/change/").status_code == 200
    )
    admin_client.post(
        "/admin/bookings/reservation/",
        {"action": "confirm_selected", "_selected_action": [reservation.pk]},
        follow=True,
    )
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.CONFIRMED
    assert any("confirmed" in m.subject.lower() for m in mail.outbox)
