"""Dashboard: today in the studio (boxes timeline and list), new requests, nearest days, period stats."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import Resource
from app.models.enums import BookingStatus
from app.schemas.booking import BookingAdminOut
from app.services import queries, stats
from app.services.availability import Interval
from app.services.snapshot import load_snapshot
from app.web.panel import fmt
from app.web.panel.common import AnyPanel, Panel, render

router = APIRouter()

Period = Literal["week", "month", "quarter"]
PERIOD_LABELS = {"week": "Неделя", "month": "Месяц", "quarter": "Квартал"}
PERIOD_GEN = {"week": "недели", "month": "месяца", "quarter": "квартала"}
PERIOD_FOR = {"week": "за неделю", "month": "за месяц", "quarter": "за квартал"}
SHOWN_ON_TIMELINE = (BookingStatus.NEW, BookingStatus.CONFIRMED, BookingStatus.DONE, BookingStatus.NO_SHOW)


@dataclass
class Segment:
    left: float  # percent of the axis
    width: float
    kind: str  # booking status or "free"
    title: str = ""
    sub: str = ""
    href: str = ""


@dataclass
class Row:
    """One line of the "today" list."""

    booking: BookingAdminOut
    time_label: str
    title: str
    sub: str
    struck: bool
    href: str


def _day_index(booking: BookingAdminOut, day: date, panel: Panel) -> tuple[int, int]:
    first = booking.starts_at.astimezone(panel.tz).date()
    last = (booking.ends_at - timedelta(seconds=1)).astimezone(panel.tz).date()
    return (day - first).days + 1, (last - first).days + 1


def _service_line(booking: BookingAdminOut, day: date, panel: Panel) -> str:
    index, total = _day_index(booking, day, panel)
    if total > 1:
        if index == total:
            return f"Выдача · {booking.service_name}"
        return f"{booking.service_name} · день {index} из {total}"
    minutes = (booking.ends_at - booking.starts_at).total_seconds() / 60
    if minutes > 8 * 60:
        return f"{booking.service_name} · до {fmt.hm(booking.ends_at.astimezone(panel.tz))}"
    return f"{booking.service_name} · {fmt.duration(minutes)}"


def _booking_href(panel: Panel, booking: BookingAdminOut) -> str:
    day = booking.starts_at.astimezone(panel.tz).date()
    return panel.url(f"/bookings?date={day.isoformat()}&open={booking.id}")


def _timeline(
    panel: Panel, bookings: list[BookingAdminOut], opening: Interval | None, resources: list[tuple[int, str]], day: date
) -> tuple[list[int], list[tuple[str, list[Segment]]]]:
    if opening is None:
        return [], []
    tz = panel.tz
    axis_start = opening.start.replace(minute=0)
    axis_end = opening.end if opening.end.minute == 0 else opening.end.replace(minute=0) + timedelta(hours=1)
    span = (axis_end - axis_start).total_seconds()
    hours = list(range(axis_start.astimezone(tz).hour, axis_end.astimezone(tz).hour))

    def pos(moment: datetime) -> float:
        moment = min(max(moment, axis_start), axis_end)
        return round(100 * (moment - axis_start).total_seconds() / span, 3)

    rows = []
    for resource_id, name in resources:
        segments: list[Segment] = []
        mine = sorted(
            (b for b in bookings if b.resource_id == resource_id and b.status in SHOWN_ON_TIMELINE),
            key=lambda b: b.starts_at,
        )
        cursor = opening.start
        for booking in mine:
            start, end = max(booking.starts_at, opening.start), min(booking.ends_at, opening.end)
            if start - cursor >= timedelta(minutes=30):
                segments.append(Segment(pos(cursor), pos(start) - pos(cursor), "free", "свободно"))
            if end > start:
                who = " · ".join(
                    x for x in (booking.contact_name or booking.client_name, booking.vehicle, booking.staff_name) if x
                )
                index, total = _day_index(booking, day, panel)
                title = booking.service_name + (f" · день {index} из {total}" if total > 1 else "")
                href = _booking_href(panel, booking)
                segments.append(Segment(pos(start), pos(end) - pos(start), booking.status, title, who, href))
            cursor = max(cursor, end)
        if opening.end - cursor >= timedelta(minutes=30):
            segments.append(Segment(pos(cursor), pos(opening.end) - pos(cursor), "free", "свободно"))
        rows.append((name, segments))
    return hours, rows


@router.get("/admin/{studio_id}/")
async def dashboard(
    request: Request,
    panel: AnyPanel,
    session: DbSession,
    period: Annotated[Period, Query()] = "week",
) -> Response:
    studio, tz = panel.studio, panel.tz
    now = panel.now()
    today = now.date()
    day_start = datetime.combine(today, time(0), tzinfo=tz)
    scope = (panel.membership.staff_id or -1) if not panel.is_manager else None

    todays = await queries.list_bookings(
        session, studio.id, date_from=day_start, date_to=day_start + timedelta(days=1), staff_id=scope
    )
    starting_today = [b for b in todays if b.starts_at >= day_start]
    counts = {s: sum(1 for b in starting_today if b.status == s) for s in BookingStatus}
    working_today = [b for b in starting_today if b.status in SHOWN_ON_TIMELINE]

    snap = await load_snapshot(session, studio, day_start, day_start + timedelta(days=1))
    resources = [
        (r.id, r.name)
        for r in await session.scalars(
            select(Resource)
            .where(Resource.studio_id == studio.id, Resource.is_active.is_(True))
            .order_by(Resource.sort_order, Resource.id)
        )
    ]
    hours, timeline = _timeline(panel, todays, snap.opening(today), resources, today)

    rows = []
    for booking in sorted(todays, key=lambda b: b.starts_at):
        continuing = booking.starts_at < day_start
        rows.append(
            Row(
                booking=booking,
                time_label="в студии" if continuing else fmt.hm(booking.starts_at.astimezone(tz)),
                title=booking.contact_name or booking.client_name or "Без имени",
                sub=_service_line(booking, today, panel),
                struck=booking.status in (BookingStatus.CANCELLED, BookingStatus.NO_SHOW),
                href=_booking_href(panel, booking),
            )
        )
    in_studio_now = [
        b for b in todays if b.starts_at <= now < b.ends_at and b.status in (BookingStatus.CONFIRMED, BookingStatus.NEW)
    ]
    later_today = [r for r in rows if r.booking.starts_at > now]

    requests = await queries.new_requests(session, studio.id, staff_id=scope, limit=20)
    # A master gets numbers about their own bookings only: the load of the boxes is the studio's business.
    period_stats = await stats.period_stats(session, studio, period, today, staff_id=scope)
    upcoming = await stats.day_loads(session, studio, today + timedelta(days=1), 5) if panel.is_manager else []
    clients = await stats.client_stats(session, studio.id, now) if panel.is_manager else None
    peak = max((count for _, count, _, _ in period_stats.per_bucket), default=0)

    return render(
        request,
        "panel/dashboard.html",
        panel,
        active="dashboard",
        now=now,
        today=today,
        greeting=fmt.greeting(now),
        period=period,
        period_labels=PERIOD_LABELS,
        period_gen=PERIOD_GEN[period],
        period_for=PERIOD_FOR[period],
        counts=counts,
        today_total=len(working_today),
        hours=hours,
        timeline=timeline,
        rows=rows,
        in_studio_now=in_studio_now,
        later_today=later_today,
        requests=requests,
        new_total=panel.new_count if panel.is_manager else len(requests),
        stats=period_stats,
        stats_last_day=period_stats.end - timedelta(days=1),
        peak=peak,
        upcoming=upcoming,
        clients=clients,
        ago=lambda moment: fmt.ago(moment, now),
        relative_day=lambda day: fmt.relative_day(day, today),
    )
