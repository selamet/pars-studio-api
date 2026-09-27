"""Availability, holds and status changes for studio reservations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import StudioRate
from apps.core.emails import send_templated_email

from . import rules
from .ics import build_ics
from .models import Reservation

logger = logging.getLogger(__name__)


class BookingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Slot:
    start: int
    durations: list[int]


def live_reservations(day: date):
    return Reservation.objects.filter(session_date=day, status__in=Reservation.LIVE_STATUSES)


def _fits(start: int, duration: int, taken: list[tuple[int, int]]) -> bool:
    end = start + duration
    if end > rules.CLOSE_HOUR:
        return False
    return not any(start < t_end and t_start < end for t_start, t_end in taken)


def is_closed(day: date) -> bool:
    return day.weekday() in rules.CLOSED_WEEKDAYS


def availability(day: date, service_type: str) -> list[Slot]:
    """Bookable start hours for `service_type` on `day`, each with the durations that fit."""
    durations = rules.DURATIONS.get(service_type)
    if not durations or is_closed(day) or day < timezone.localdate():
        return []
    taken = [(r.slot.lower, r.slot.upper) for r in live_reservations(day)]
    slots = []
    for start in rules.start_hours():
        fitting = [d for d in durations if _fits(start, d, taken)]
        if fitting:
            slots.append(Slot(start=start, durations=fitting))
    return slots


def price_for(service_type: str, duration_hours: int) -> Decimal:
    rate = StudioRate.objects.filter(service_type=service_type, is_active=True).first()
    if rate is None:
        raise BookingError("no_rate", "This session type cannot be booked online right now.")
    return rate.hourly_price_usd * duration_hours


def validate_request(service_type: str, day: date, start: time, duration_hours: int) -> None:
    today = timezone.localdate()
    if service_type not in rules.DURATIONS:
        raise BookingError("invalid_service", "Unknown session type.")
    if duration_hours not in rules.DURATIONS[service_type]:
        raise BookingError(
            "invalid_duration", "This duration is not offered for that session type."
        )
    if day < today:
        raise BookingError("past_date", "That date is in the past.")
    if day > today + timedelta(days=rules.MAX_ADVANCE_DAYS):
        raise BookingError("too_far", f"Bookings open {rules.MAX_ADVANCE_DAYS} days ahead.")
    if is_closed(day):
        raise BookingError("closed", "The studio is closed that day.")
    if start.minute or start.second:
        raise BookingError("invalid_time", "Sessions start on the hour.")
    if start.hour < rules.OPEN_HOUR or start.hour + duration_hours > rules.CLOSE_HOUR:
        raise BookingError("outside_hours", "That session runs outside opening hours.")
    if day == today and start.hour <= timezone.localtime().hour:
        raise BookingError("past_time", "That start time has already passed.")


def create_hold(user, data: dict, *, hold_until: datetime, locale: str) -> Reservation:
    """
    Reserve the slot until payment. Raises BookingError('slot_taken') when the
    exclusion constraint rejects the overlap.
    """
    validate_request(
        data["service_type"], data["session_date"], data["start_time"], data["duration_hours"]
    )
    price = price_for(data["service_type"], data["duration_hours"])
    reservation = Reservation(
        user=user,
        customer_name=data["customer_name"],
        customer_email=user.email,
        customer_phone=data["customer_phone"],
        artist_name=data.get("artist_name", ""),
        service_type=data["service_type"],
        session_date=data["session_date"],
        start_time=data["start_time"],
        duration_hours=data["duration_hours"],
        project_description=data.get("project_description", ""),
        reference_links=data.get("reference_links", ""),
        status=Reservation.Status.HOLD,
        locale=locale,
        price_usd=price,
        hold_expires_at=hold_until,
    )
    try:
        with transaction.atomic():
            reservation.save()
    except IntegrityError as exc:
        raise BookingError(
            "slot_taken", "That time was just taken. Please pick another slot."
        ) from exc
    return reservation


def release_hold(reservation: Reservation, *, to=Reservation.Status.EXPIRED) -> None:
    if reservation.status == Reservation.Status.HOLD:
        reservation.status = to
        reservation.save(update_fields=["status", "updated_at"])


def confirm(reservation: Reservation) -> None:
    """Payment arrived: lock the slot in and tell everyone."""
    if reservation.status != Reservation.Status.HOLD:
        return
    reservation.status = Reservation.Status.CONFIRMED
    reservation.hold_expires_at = None
    reservation.save(update_fields=["status", "hold_expires_at", "updated_at"])
    context = {"reservation": reservation, "locale": reservation.locale}
    send_templated_email(
        "booking_confirmed",
        context,
        [reservation.customer_email],
        attachments=[
            [f"pars-studio-{reservation.code}.ics", build_ics(reservation), "text/calendar"]
        ],
    )
    send_templated_email("booking_notification", context, [settings.STUDIO_NOTIFICATION_EMAIL])


def cancel(reservation: Reservation, *, notify: bool = True) -> None:
    if reservation.status not in (Reservation.Status.HOLD, Reservation.Status.CONFIRMED):
        return
    was_confirmed = reservation.status == Reservation.Status.CONFIRMED
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    if notify and was_confirmed:
        send_templated_email(
            "booking_cancelled",
            {"reservation": reservation, "locale": reservation.locale},
            [reservation.customer_email],
        )


def expire_holds(now=None) -> int:
    now = now or timezone.now()
    stale = Reservation.objects.filter(status=Reservation.Status.HOLD, hold_expires_at__lt=now)
    count = stale.update(status=Reservation.Status.EXPIRED)
    if count:
        logger.info("Expired %d reservation hold(s)", count)
    return count
