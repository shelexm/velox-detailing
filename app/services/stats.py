"""Numbers for the panel dashboard: load of boxes, bookings per day and per service, client counts.

Load is measured in slot units (studio slot step): capacity is the opening time of every active box,
busy time is the union of bookings and blocks on each box, clipped to the opening hours.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Client, Studio
from app.models.enums import BookingStatus
from app.services.availability import Interval
from app.services.snapshot import load_snapshot

# Bookings that really use (or used) the studio's time.
WORK_STATUSES = (BookingStatus.NEW, BookingStatus.CONFIRMED, BookingStatus.DONE, BookingStatus.NO_SHOW)


@dataclass
class DayLoad:
    day: date
    is_open: bool
    total: int = 0  # slots of capacity (boxes x opening / step)
    busy: int = 0  # slots taken by bookings
    blocked: int = 0  # slots taken by blocks

    @property
    def free(self) -> int:
        return max(0, self.total - self.busy - self.blocked)

    @property
    def share(self) -> float:
        return (self.busy + self.blocked) / self.total if self.total else 0.0


@dataclass
class PeriodStats:
    start: date
    end: date  # exclusive
    loads: list[DayLoad]
    per_bucket: list[tuple[str, int, bool, bool]]  # label, count, is_current, is_future
    by_service: list[tuple[str, int]]
    done: int = 0
    cancelled: int = 0
    no_show: int = 0
    busy_slots: int = 0
    total_slots: int = 0

    @property
    def load_percent(self) -> int:
        return round(100 * self.busy_slots / self.total_slots) if self.total_slots else 0


@dataclass
class ClientStats:
    total: int
    new_30_days: int
    repeat_percent: int


def _merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for item in sorted(intervals, key=lambda i: i.start):
        if merged and item.start <= merged[-1].end:
            if item.end > merged[-1].end:
                merged[-1] = Interval(merged[-1].start, item.end)
        else:
            merged.append(item)
    return merged


def _clip(intervals: list[Interval], window: Interval) -> list[Interval]:
    return [Interval(max(i.start, window.start), min(i.end, window.end)) for i in intervals if i.overlaps(window)]


def _minutes(intervals: list[Interval]) -> float:
    return sum((i.end - i.start).total_seconds() for i in intervals) / 60


async def day_loads(session: AsyncSession, studio: Studio, first: date, days: int) -> list[DayLoad]:
    start = datetime.combine(first, time(0), tzinfo=_tz(studio))
    end = start + timedelta(days=days)
    snap = await load_snapshot(session, studio, start, end)
    rows = await session.execute(
        select(Booking.resource_id, Booking.starts_at, Booking.ends_at).where(
            Booking.studio_id == studio.id,
            Booking.resource_id.is_not(None),
            Booking.status.in_(WORK_STATUSES),
            Booking.starts_at < end,
            Booking.ends_at > start,
        )
    )
    by_resource: dict[int, list[Interval]] = defaultdict(list)
    for resource_id, starts_at, ends_at in rows.all():
        by_resource[resource_id].append(Interval(starts_at, ends_at))
    step = max(1, studio.slot_step_minutes)

    result = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        opening = snap.opening(day)
        if opening is None or not snap.resource_ids:
            result.append(DayLoad(day, is_open=opening is not None))
            continue
        total = busy = blocked = 0.0
        for resource_id in snap.resource_ids:
            total += _minutes([opening])
            booked = _merge(_clip(by_resource.get(resource_id, []), opening))
            blocks = _merge(_clip(snap.studio_blocks + snap.resource_blocks.get(resource_id, []), opening))
            busy += _minutes(booked)
            # Blocked time that is not already covered by a booking.
            blocked += max(0.0, _minutes(_merge(booked + blocks)) - _minutes(booked))
        result.append(DayLoad(day, True, round(total / step), round(busy / step), round(blocked / step)))
    return result


WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_SHORT = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def period_bounds(period: str, today: date) -> tuple[date, date]:
    if period == "month":
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
    elif period == "quarter":
        start = today.replace(month=(today.month - 1) // 3 * 3 + 1, day=1)
        end = (start + timedelta(days=95)).replace(day=1)
    else:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    return start, end


async def period_stats(session: AsyncSession, studio: Studio, period: str, today: date) -> PeriodStats:
    start_day, end_day = period_bounds(period, today)
    loads = await day_loads(session, studio, start_day, (end_day - start_day).days)
    tz_start = datetime.combine(start_day, time(0), tzinfo=_tz(studio))
    tz_end = datetime.combine(end_day, time(0), tzinfo=_tz(studio))
    rows = (
        await session.execute(
            select(Booking.starts_at, Booking.status, Booking.service_name).where(
                Booking.studio_id == studio.id, Booking.starts_at >= tz_start, Booking.starts_at < tz_end
            )
        )
    ).all()
    statuses = Counter(status for _, status, _ in rows)
    tz = _tz(studio)
    working = [(starts_at.astimezone(tz).date(), name) for starts_at, status, name in rows if status in WORK_STATUSES]

    buckets: list[tuple[str, int, bool, bool]] = []
    if period == "week":
        per_day = Counter(day for day, _ in working)
        for offset in range(7):
            day = start_day + timedelta(days=offset)
            buckets.append((WEEKDAYS_SHORT[day.weekday()], per_day[day], day == today, day > today))
    elif period == "month":
        week = start_day - timedelta(days=start_day.weekday())
        while week < end_day:
            count = sum(1 for day, _ in working if week <= day < week + timedelta(days=7))
            label = f"{max(week, start_day).day}–{min(week + timedelta(days=6), end_day - timedelta(days=1)).day}"
            buckets.append((label, count, week <= today < week + timedelta(days=7), week > today))
            week += timedelta(days=7)
    else:
        month = start_day
        while month < end_day:
            nxt = (month + timedelta(days=32)).replace(day=1)
            count = sum(1 for day, _ in working if month <= day < nxt)
            buckets.append((MONTHS_SHORT[month.month - 1], count, month <= today < nxt, month > today))
            month = nxt

    return PeriodStats(
        start=start_day,
        end=end_day,
        loads=loads,
        per_bucket=buckets,
        by_service=Counter(name for _, name in working).most_common(4),
        done=statuses[BookingStatus.DONE],
        cancelled=statuses[BookingStatus.CANCELLED],
        no_show=statuses[BookingStatus.NO_SHOW],
        busy_slots=sum(d.busy for d in loads),
        total_slots=sum(d.total - d.blocked for d in loads),
    )


def _tz(studio: Studio) -> ZoneInfo:
    return ZoneInfo(studio.timezone)


async def client_stats(session: AsyncSession, studio_id: int, now: datetime) -> ClientStats:
    total = await session.scalar(select(func.count()).select_from(Client).where(Client.studio_id == studio_id)) or 0
    new = (
        await session.scalar(
            select(func.count())
            .select_from(Client)
            .where(Client.studio_id == studio_id, Client.created_at >= now - timedelta(days=30))
        )
        or 0
    )
    visits = (
        select(Booking.client_id, func.count().label("n"))
        .where(Booking.studio_id == studio_id, Booking.status == BookingStatus.DONE)
        .group_by(Booking.client_id)
        .subquery()
    )
    with_visits = await session.scalar(select(func.count()).select_from(visits)) or 0
    repeat = await session.scalar(select(func.count()).select_from(visits).where(visits.c.n > 1)) or 0
    share = round(100 * repeat / with_visits) if with_visits else 0
    return ClientStats(total=total, new_30_days=new, repeat_percent=share)


@dataclass
class StaffDay:
    day: date
    working: bool
    absent: bool = False
    percent: int = 0
    window: Interval | None = None


async def staff_week(session: AsyncSession, studio: Studio, first: date) -> dict[int, list[StaffDay]]:
    """Per master and day: is the master working (own shift inside the studio hours, not absent) and how
    much of that shift is booked, in percent."""
    tz = _tz(studio)
    start = datetime.combine(first, time(0), tzinfo=tz)
    end = start + timedelta(days=7)
    snap = await load_snapshot(session, studio, start, end)
    rows = await session.execute(
        select(Booking.staff_id, Booking.starts_at, Booking.ends_at).where(
            Booking.studio_id == studio.id,
            Booking.staff_id.is_not(None),
            Booking.status.in_(WORK_STATUSES),
            Booking.starts_at < end,
            Booking.ends_at > start,
        )
    )
    by_staff: dict[int, list[Interval]] = defaultdict(list)
    for staff_id, starts_at, ends_at in rows.all():
        by_staff[staff_id].append(Interval(starts_at, ends_at))

    result: dict[int, list[StaffDay]] = {}
    for staff_id, hours in snap.staff_hours.items():
        days = []
        for offset in range(7):
            day = first + timedelta(days=offset)
            absent = any(a <= day <= b for a, b in snap.staff_absences.get(staff_id, []))
            shift, opening = hours.get(day.weekday()), snap.opening(day)
            if absent or shift is None or opening is None:
                days.append(StaffDay(day, working=False, absent=absent))
                continue
            window = Interval(
                max(opening.start, snap.at(day, shift.opens)), min(opening.end, snap.at(day, shift.closes))
            )
            if window.end <= window.start:
                days.append(StaffDay(day, working=False))
                continue
            busy = _minutes(_merge(_clip(by_staff.get(staff_id, []), window)))
            days.append(StaffDay(day, True, percent=round(100 * busy / _minutes([window])), window=window))
        result[staff_id] = days
    return result
