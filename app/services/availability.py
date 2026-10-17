"""Slot availability: pure functions over a snapshot of one studio's schedule. No database access here.

Rules (from the "Слоты и вместимость" and "Расписание" screens of the design):
- slots start on a grid of `slot_step` from the opening time; a slot needs a free box (if the service uses one)
  and a free eligible master (if the service needs one);
- a break or a whole-studio block forbids starting inside it; a same-day service must also fit before closing
  and must not overlap a whole-studio block;
- a multi-day service ends at the closing time of its N-th working day and keeps its box and master the whole time;
- after every booking the box and the master stay busy for `buffer` minutes;
- online starts must be at least `min_lead` from now and within `horizon_days`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# A multi-day job must start early enough to make use of its first day.
MULTIDAY_MIN_FIRST_DAY = timedelta(hours=4)
_MAX_SCAN_DAYS = 90


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


@dataclass(frozen=True)
class Hours:
    opens: time
    closes: time


@dataclass(frozen=True)
class Rules:
    timezone: ZoneInfo
    slot_step: timedelta
    buffer: timedelta
    min_lead: timedelta
    horizon_days: int
    respect_staff_availability: bool = True


@dataclass(frozen=True)
class ServiceSpec:
    id: int
    duration_minutes: int | None
    duration_days: int | None
    requires_resource: bool
    requires_staff: bool
    staff_ids: tuple[int, ...] = ()  # eligible masters, in preference order


@dataclass
class StudioSnapshot:
    rules: Rules
    weekly_hours: dict[int, Hours | None]
    breaks: dict[int, list[tuple[time, time]]] = field(default_factory=dict)
    special_days: dict[date, Hours | None] = field(default_factory=dict)
    resource_ids: list[int] = field(default_factory=list)
    staff_hours: dict[int, dict[int, Hours | None]] = field(default_factory=dict)
    staff_absences: dict[int, list[tuple[date, date]]] = field(default_factory=dict)
    studio_blocks: list[Interval] = field(default_factory=list)
    resource_blocks: dict[int, list[Interval]] = field(default_factory=dict)
    staff_blocks: dict[int, list[Interval]] = field(default_factory=dict)
    resource_busy: dict[int, list[Interval]] = field(default_factory=dict)
    staff_busy: dict[int, list[Interval]] = field(default_factory=dict)

    @property
    def tz(self) -> ZoneInfo:
        return self.rules.timezone

    def at(self, day: date, moment: time) -> datetime:
        return datetime.combine(day, moment, tzinfo=self.tz)

    def local_date(self, moment: datetime) -> date:
        return moment.astimezone(self.tz).date()

    def hours_on(self, day: date) -> Hours | None:
        if day in self.special_days:
            return self.special_days[day]
        return self.weekly_hours.get(day.weekday())

    def opening(self, day: date) -> Interval | None:
        hours = self.hours_on(day)
        if hours is None:
            return None
        return Interval(self.at(day, hours.opens), self.at(day, hours.closes))


@dataclass(frozen=True)
class Assignment:
    start: datetime
    end: datetime
    occupied_until: datetime
    resource_id: int | None
    staff_id: int | None


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime
    available: bool
    free_places: int
    total_places: int
    blocked: bool = False


def _any_overlap(intervals: Iterable[Interval], target: Interval) -> bool:
    return any(item.overlaps(target) for item in intervals)


def service_end(snap: StudioSnapshot, service: ServiceSpec, start: datetime) -> datetime | None:
    """When the work ends, or None if the service cannot start at this moment."""
    day = snap.local_date(start)
    opening = snap.opening(day)
    if opening is None or not opening.contains(start):
        return None
    if service.duration_minutes is not None:
        end = start + timedelta(minutes=service.duration_minutes)
        return end if end <= opening.end else None
    if start > opening.end - MULTIDAY_MIN_FIRST_DAY:
        return None
    remaining = (service.duration_days or 1) - 1
    current = day
    for _ in range(_MAX_SCAN_DAYS):
        if remaining == 0:
            closing = snap.opening(current)
            return closing.end if closing else None
        current += timedelta(days=1)
        if snap.opening(current) is not None:
            remaining -= 1
    return None


def _in_break(snap: StudioSnapshot, start: datetime) -> bool:
    day = snap.local_date(start)
    return any(
        Interval(snap.at(day, begins), snap.at(day, ends)).contains(start)
        for begins, ends in snap.breaks.get(day.weekday(), [])
    )


def _studio_blocked(snap: StudioSnapshot, service: ServiceSpec, start: datetime, end: datetime) -> bool:
    work = Interval(start, end)
    for block in snap.studio_blocks:
        if block.contains(start):
            return True
        if service.duration_minutes is not None and block.overlaps(work):
            return True
    return False


def start_blocked(snap: StudioSnapshot, start: datetime) -> bool:
    """A break or a whole-studio block: such start times are not shown to clients at all."""
    return _in_break(snap, start) or any(block.contains(start) for block in snap.studio_blocks)


def _resource_free(snap: StudioSnapshot, resource_id: int, work: Interval, occupied: Interval) -> bool:
    return not _any_overlap(snap.resource_blocks.get(resource_id, []), work) and not _any_overlap(
        snap.resource_busy.get(resource_id, []), occupied
    )


def _staff_free(snap: StudioSnapshot, staff_id: int, service: ServiceSpec, work: Interval, occupied: Interval) -> bool:
    day = snap.local_date(work.start)
    hours = snap.staff_hours.get(staff_id, {}).get(day.weekday())
    if hours is None:
        return False
    shift = Interval(snap.at(day, hours.opens), snap.at(day, hours.closes))
    if service.duration_minutes is not None:
        if not (shift.start <= work.start and work.end <= shift.end):
            return False
    elif not shift.contains(work.start):
        return False
    last_day = snap.local_date(work.end - timedelta(microseconds=1))
    for absent_from, absent_to in snap.staff_absences.get(staff_id, []):
        if absent_from <= last_day and day <= absent_to:
            return False
    if _any_overlap(snap.staff_blocks.get(staff_id, []), work):
        return False
    return not _any_overlap(snap.staff_busy.get(staff_id, []), occupied)


def within_booking_window(snap: StudioSnapshot, start: datetime, now: datetime) -> bool:
    if start < now + snap.rules.min_lead:
        return False
    last_day = snap.local_date(now) + timedelta(days=snap.rules.horizon_days)
    return snap.local_date(start) <= last_day


def on_grid(snap: StudioSnapshot, start: datetime) -> bool:
    opening = snap.opening(snap.local_date(start))
    if opening is None or not opening.contains(start):
        return False
    return (start - opening.start) % snap.rules.slot_step == timedelta(0)


def assign(
    snap: StudioSnapshot,
    service: ServiceSpec,
    start: datetime,
    *,
    now: datetime,
    staff_id: int | None = None,
    enforce_window: bool = True,
    allow_blocked_start: bool = False,
) -> Assignment | None:
    """Pick a free box and master for `start`, or None when the slot is not available."""
    if enforce_window and not within_booking_window(snap, start, now):
        return None
    end = service_end(snap, service, start)
    if end is None:
        return None
    if not allow_blocked_start and (_in_break(snap, start) or _studio_blocked(snap, service, start, end)):
        return None
    work = Interval(start, end)
    occupied_until = end + snap.rules.buffer
    occupied = Interval(start, occupied_until)

    resource_id = None
    if service.requires_resource:
        resource_id = next((r for r in snap.resource_ids if _resource_free(snap, r, work, occupied)), None)
        if resource_id is None:
            return None

    chosen_staff = None
    if service.requires_staff:
        if staff_id is not None and staff_id not in service.staff_ids:
            return None
        candidates = (staff_id,) if staff_id is not None else service.staff_ids
        chosen_staff = next((s for s in candidates if _staff_free(snap, s, service, work, occupied)), None)
        if chosen_staff is None and (staff_id is not None or snap.rules.respect_staff_availability):
            return None
    return Assignment(start, end, occupied_until, resource_id, chosen_staff)


def total_places(snap: StudioSnapshot, service: ServiceSpec) -> int:
    if service.requires_resource:
        return len(snap.resource_ids)
    if service.requires_staff:
        return len(service.staff_ids)
    return 1


def free_places(snap: StudioSnapshot, service: ServiceSpec, start: datetime, end: datetime) -> int:
    work = Interval(start, end)
    occupied = Interval(start, end + snap.rules.buffer)
    counts = []
    if service.requires_resource:
        counts.append(sum(1 for r in snap.resource_ids if _resource_free(snap, r, work, occupied)))
    if service.requires_staff and snap.rules.respect_staff_availability:
        counts.append(sum(1 for s in service.staff_ids if _staff_free(snap, s, service, work, occupied)))
    return min(counts) if counts else 1


def grid_starts(snap: StudioSnapshot, day: date) -> list[datetime]:
    opening = snap.opening(day)
    if opening is None:
        return []
    starts = []
    current = opening.start
    while current < opening.end:
        starts.append(current)
        current += snap.rules.slot_step
    return starts


def day_slots(
    snap: StudioSnapshot,
    service: ServiceSpec,
    day: date,
    *,
    now: datetime,
    staff_id: int | None = None,
    include_blocked: bool = False,
) -> list[Slot]:
    """Grid slots of one day for a service. Past and too-soon slots are omitted."""
    slots = []
    for start in grid_starts(snap, day):
        if not within_booking_window(snap, start, now):
            continue
        end = service_end(snap, service, start)
        if end is None:
            continue
        blocked = start_blocked(snap, start)
        if blocked and not include_blocked:
            continue
        assignment = None if blocked else assign(snap, service, start, now=now, staff_id=staff_id)
        places = 0 if blocked else free_places(snap, service, start, end)
        slots.append(
            Slot(
                start=start,
                end=end,
                available=assignment is not None,
                free_places=places if assignment is not None else 0,
                total_places=total_places(snap, service),
                blocked=blocked,
            )
        )
    return slots


def nearest_available(
    snap: StudioSnapshot,
    service: ServiceSpec,
    after: datetime,
    *,
    now: datetime,
    staff_id: int | None = None,
    limit: int = 3,
    max_days: int = 14,
) -> list[datetime]:
    """The next free grid starts from `after` (used to suggest alternatives when a slot was just taken)."""
    found: list[datetime] = []
    first_day = snap.local_date(after)
    for offset in range(max_days):
        day = first_day + timedelta(days=offset)
        for slot in day_slots(snap, service, day, now=now, staff_id=staff_id):
            if slot.available and slot.start >= after:
                found.append(slot.start)
                if len(found) >= limit:
                    return found
    return found
