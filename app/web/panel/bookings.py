"""Bookings calendar: week (columns are days) and day (columns are boxes), a list, and the edit panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.models import Resource, Service, Staff
from app.models.enums import BookingSource, BookingStatus
from app.schemas.booking import BookingAdminOut
from app.schemas.common import MAX_DAY, MIN_DAY
from app.services import queries
from app.services.booking import TRANSITIONS
from app.services.snapshot import load_snapshot
from app.web.panel import fmt
from app.web.panel.common import AnyPanel, Panel, render

router = APIRouter()

View = Literal["week", "day", "list"]
HOUR_PX = 64
STATUS_ORDER = (
    BookingStatus.NEW,
    BookingStatus.CONFIRMED,
    BookingStatus.DONE,
    BookingStatus.NO_SHOW,
    BookingStatus.CANCELLED,
)
SOURCE_LABELS = {
    BookingSource.SITE: "через сайт",
    BookingSource.TELEGRAM: "через Telegram",
    BookingSource.ADMIN: "в панели",
    BookingSource.PHONE: "по телефону",
}


@dataclass
class Block:
    booking: BookingAdminOut
    top: float
    height: float
    lane: int = 0
    lanes: int = 1
    time_label: str = ""
    all_day: bool = False

    @property
    def left(self) -> float:
        return round(100 * self.lane / self.lanes, 3)

    @property
    def width(self) -> float:
        return round(100 / self.lanes, 3)


@dataclass
class Column:
    key: str
    label: str
    sub: str = ""
    is_today: bool = False
    day: date | None = None
    count: int = 0
    blocks: list[Block] = field(default_factory=list)
    closed: bool = False


@dataclass
class Span:
    """A multi-day job in the "в студии" lane of the week view."""

    booking: BookingAdminOut
    start_col: int
    end_col: int
    row: int


def _lanes(blocks: list[Block]) -> None:
    """Overlapping bookings of one column share its width, as in the mockup."""
    blocks.sort(key=lambda b: (b.top, -b.height))
    cluster: list[Block] = []
    cluster_end = -1.0
    ends: list[float] = []

    def close() -> None:
        lanes = max((b.lane for b in cluster), default=0) + 1
        for b in cluster:
            b.lanes = lanes

    for block in blocks:
        if cluster and block.top >= cluster_end:
            close()
            cluster, ends = [], []
        free = next((i for i, end in enumerate(ends) if end <= block.top), None)
        if free is None:
            ends.append(block.top + block.height)
            block.lane = len(ends) - 1
        else:
            ends[free] = block.top + block.height
            block.lane = free
        cluster.append(block)
        cluster_end = max(cluster_end, block.top + block.height)
    if cluster:
        close()


def _local(moment: datetime, panel: Panel) -> datetime:
    return moment.astimezone(panel.tz)


def _is_multiday(b: BookingAdminOut, panel: Panel) -> bool:
    return _local(b.starts_at, panel).date() != _local(b.ends_at - timedelta(seconds=1), panel).date()


async def _hours_range(session, panel: Panel, first: date, days: int) -> tuple[int, int, dict[date, bool]]:
    start = datetime.combine(first, time(0), tzinfo=panel.tz)
    snap = await load_snapshot(session, panel.studio, start, start + timedelta(days=days))
    lo, hi, closed = 24, 0, {}
    for offset in range(days):
        day = first + timedelta(days=offset)
        hours = snap.hours_on(day)
        closed[day] = hours is None
        if hours:
            lo = min(lo, hours.opens.hour)
            hi = max(hi, hours.closes.hour + (1 if hours.closes.minute else 0))
    if lo >= hi:
        lo, hi = 9, 21
    return lo, hi, closed


def _block(b: BookingAdminOut, panel: Panel, day: date, lo: int, hi: int) -> Block | None:
    axis_start = datetime.combine(day, time(lo), tzinfo=panel.tz)
    axis_end = datetime.combine(day, time(0), tzinfo=panel.tz) + timedelta(hours=hi)
    start, end = max(b.starts_at, axis_start), min(b.ends_at, axis_end)
    if end <= start:
        return None
    top = (start - axis_start).total_seconds() / 3600 * HOUR_PX
    height = max(22.0, (end - start).total_seconds() / 3600 * HOUR_PX - 2)
    all_day = _is_multiday(b, panel)
    label = "весь день" if all_day else f"{fmt.hm(_local(b.starts_at, panel))}–{fmt.hm(_local(b.ends_at, panel))}"
    return Block(b, round(top, 1), round(height, 1), time_label=label, all_day=all_day)


async def active_staff(session, studio_id: int) -> list[Staff]:
    query = select(Staff).where(Staff.studio_id == studio_id, Staff.is_active.is_(True))
    return list((await session.scalars(query.order_by(Staff.sort_order, Staff.id))).all())


async def _form_options(session, panel: Panel) -> dict:
    services = (
        await session.scalars(
            select(Service)
            .where(Service.studio_id == panel.studio.id, Service.is_active.is_(True))
            .order_by(Service.sort_order, Service.id)
        )
    ).all()
    staff = await active_staff(session, panel.studio.id)
    return {"services": services, "staff": staff}


@router.get("/admin/{studio_id}/bookings")
async def bookings_page(
    request: Request,
    panel: AnyPanel,
    session: DbSession,
    view: Annotated[View, Query()] = "week",
    day: Annotated[date | None, Query(alias="date", ge=MIN_DAY, le=MAX_DAY)] = None,
    staff: Annotated[int | None, Query(ge=1)] = None,
    status: Annotated[BookingStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
    new: Annotated[bool, Query()] = False,
    client: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    tz, now = panel.tz, panel.now()
    today = now.date()
    day = day or today
    if status is not None or q:
        view = "list"
    scope = None if panel.is_manager else (panel.membership.staff_id or -1)
    staff_filter = scope if scope is not None else staff

    if view == "week":
        first, days = day - timedelta(days=day.weekday()), 7
    elif view == "day":
        first, days = day, 1
    else:
        first, days = day - timedelta(days=day.weekday()), 7

    window_start = datetime.combine(first, time(0), tzinfo=tz)
    window_end = window_start + timedelta(days=days)
    if view == "list" and (status is not None or q):
        # Requests and search look across the whole horizon, not only one week.
        window_start = datetime.combine(today - timedelta(days=60), time(0), tzinfo=tz)
        window_end = datetime.combine(today + timedelta(days=panel.studio.horizon_days + 60), time(0), tzinfo=tz)
    bookings = await queries.list_bookings(
        session,
        panel.studio.id,
        date_from=window_start,
        date_to=window_end,
        statuses=[status] if status else None,
        staff_id=staff_filter,
        query=q,
    )

    lo, hi, closed = await _hours_range(session, panel, first, days)
    columns: list[Column] = []
    spans: list[Span] = []
    if view == "week":
        for offset in range(7):
            d = first + timedelta(days=offset)
            columns.append(
                Column(d.isoformat(), fmt.WEEKDAYS_SHORT[d.weekday()], str(d.day), d == today, d, closed=closed[d])
            )
        rows_end: list[int] = []
        for b in bookings:
            if _is_multiday(b, panel):
                s_col = max(0, (_local(b.starts_at, panel).date() - first).days)
                e_col = min(6, (_local(b.ends_at - timedelta(seconds=1), panel).date() - first).days)
                row = next((i for i, end in enumerate(rows_end) if end < s_col), None)
                if row is None:
                    rows_end.append(e_col)
                    row = len(rows_end) - 1
                else:
                    rows_end[row] = e_col
                spans.append(Span(b, s_col, e_col, row))
                for c in range(s_col, e_col + 1):
                    columns[c].count += 1
                continue
            col = (_local(b.starts_at, panel).date() - first).days
            if 0 <= col < 7:
                columns[col].count += 1
                block = _block(b, panel, columns[col].day, lo, hi)
                if block:
                    columns[col].blocks.append(block)
    elif view == "day":
        resources = (
            await session.scalars(
                select(Resource)
                .where(Resource.studio_id == panel.studio.id, Resource.is_active.is_(True))
                .order_by(Resource.sort_order, Resource.id)
            )
        ).all()
        by_key = {r.id: Column(f"r{r.id}", r.name, day=day, closed=closed[day]) for r in resources}
        loose = Column("none", "Без бокса", "осмотры и выдачи", day=day, closed=closed[day])
        for b in bookings:
            target = by_key.get(b.resource_id) if b.resource_id else loose
            if target is None:
                target = loose
            block = _block(b, panel, day, lo, hi)
            if block:
                target.blocks.append(block)
                target.count += 1
        columns = list(by_key.values()) + ([loose] if loose.blocks else [])
    for column in columns:
        _lanes(column.blocks)

    detail = None
    allowed: list[str] = []
    if open_id:
        try:
            detail = await queries.booking_detail(session, panel.studio.id, open_id, staff_id=scope)
        except NotFoundError:
            detail = None
        if detail:
            allowed = [s.value for s in TRANSITIONS.get(detail.status, frozenset())]
    options = await _form_options(session, panel) if (detail or new) and panel.is_manager else {}
    prefill = None
    if new and client and panel.is_manager:
        try:
            prefill = await queries.client_detail(session, panel.studio.id, client)
        except NotFoundError:
            prefill = None

    now_top = None
    if lo <= now.hour < hi and first <= today < first + timedelta(days=days):
        now_top = round(((now.hour - lo) * 60 + now.minute) / 60 * HOUR_PX, 1)

    capacity = len(
        (
            await session.scalars(
                select(Resource.id).where(Resource.studio_id == panel.studio.id, Resource.is_active.is_(True))
            )
        ).all()
    )
    staff_list = await active_staff(session, panel.studio.id)
    last = first + timedelta(days=days - 1)
    if view == "day":
        caption = fmt.date_caption(day)
    elif first.month == last.month:
        caption = f"НЕДЕЛЯ · {first.day}–{last.day} {fmt.MONTHS_GEN[last.month - 1]} {last.year}".upper()
    else:
        caption = (
            f"НЕДЕЛЯ · {first.day} {fmt.MONTHS_GEN[first.month - 1]} – {last.day} {fmt.MONTHS_GEN[last.month - 1]}"
        ).upper()
    step = timedelta(days=1 if view == "day" else 7)

    return render(
        request,
        "panel/bookings.html",
        panel,
        active="bookings",
        view=view,
        day=day,
        today=today,
        first=first,
        prev_day=(day - step).isoformat(),
        next_day=(day + step).isoformat(),
        caption=caption,
        columns=columns,
        spans=spans,
        span_rows=max((s.row for s in spans), default=-1) + 1,
        hours=list(range(lo, hi)),
        hour_px=HOUR_PX,
        now_top=now_top,
        bookings=bookings,
        status=status,
        q=q or "",
        staff_filter=staff,
        staff_list=staff_list,
        capacity=capacity,
        detail=detail,
        allowed=allowed,
        creating=new and panel.is_manager,
        prefill=prefill,
        options=options,
        status_order=STATUS_ORDER,
        source_labels=SOURCE_LABELS,
        week_days=[first + timedelta(days=i) for i in range(7)]
        if view != "day"
        else [day - timedelta(days=day.weekday()) + timedelta(days=i) for i in range(7)],
    )


@router.get("/admin/{studio_id}/bookings/{booking_id}")
async def booking_page(request: Request, panel: AnyPanel, session: DbSession, booking_id: int) -> Response:
    """Full-screen card of one booking (phones open this instead of the side panel)."""
    scope = None if panel.is_manager else (panel.membership.staff_id or -1)
    detail = await queries.booking_detail(session, panel.studio.id, booking_id, staff_id=scope)
    options = await _form_options(session, panel) if panel.is_manager else {}
    return render(
        request,
        "panel/booking.html",
        panel,
        active="bookings",
        detail=detail,
        allowed=[s.value for s in TRANSITIONS.get(detail.status, frozenset())],
        options=options,
        status_order=STATUS_ORDER,
        source_labels=SOURCE_LABELS,
        today=panel.now().date(),
    )
