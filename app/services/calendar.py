"""iCalendar (.ics) export for "Добавить в календарь"."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Booking, Studio


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def booking_ics(booking: Booking, studio: Studio, *, host: str) -> str:
    location = ", ".join(part for part in (studio.city, studio.address) if part)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VELOX Detailing Studio//Booking//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:booking-{booking.studio_id}-{booking.number}@{host}",
        f"DTSTAMP:{_stamp(datetime.now(UTC))}",
        f"DTSTART:{_stamp(booking.starts_at)}",
        f"DTEND:{_stamp(booking.ends_at)}",
        f"SUMMARY:{_escape(f'{studio.name}: {booking.service_name}')}",
        f"DESCRIPTION:{_escape(f'Запись № {booking.number}')}",
    ]
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
