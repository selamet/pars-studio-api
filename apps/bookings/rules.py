"""Studio scheduling rules. Exposed to the frontend through /api/v1/bookings/config."""

OPEN_HOUR = 10
CLOSE_HOUR = 22
# Python weekday(): Monday = 0 … Sunday = 6. The studio is closed on Sundays.
CLOSED_WEEKDAYS = frozenset({6})
MAX_ADVANCE_DAYS = 90
ALL_DURATIONS = (1, 2, 4, 8)
# Allowed session lengths per service type.
DURATIONS = {
    "recording": (2, 4, 8),
    "mixing": (4, 8),
    "mastering": (1, 2),
    "beat": (4, 8),
    "vocal": (2, 4),
}


def start_hours() -> range:
    return range(OPEN_HOUR, CLOSE_HOUR)
