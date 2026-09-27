from datetime import UTC, datetime, timedelta

from .models import Reservation

LOCATION = "Pars Studio, Bilgiç Sokak No:2, Kağıthane, İstanbul"


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics(reservation: Reservation) -> str:
    start = datetime.combine(reservation.session_date, reservation.start_time)
    end = start + timedelta(hours=reservation.duration_hours)
    label = "Rezervasyon kodu" if reservation.locale == "tr" else "Reservation code"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Pars Studio//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:reservation-{reservation.pk}@studiospars.com",
        f"DTSTAMP:{_stamp(datetime.now(UTC))}Z",
        f"DTSTART;TZID=Europe/Istanbul:{_stamp(start)}",
        f"DTEND;TZID=Europe/Istanbul:{_stamp(end)}",
        f"SUMMARY:Pars Studio — {reservation.get_service_type_display()} (#{reservation.code})",
        f"LOCATION:{LOCATION}",
        f"DESCRIPTION:{label} #{reservation.code}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
