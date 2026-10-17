"""Load a StudioSnapshot (schedule, blocks and current occupancy) for a time window from the database."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import (
    Booking,
    Resource,
    Service,
    ServiceStaff,
    SpecialDay,
    Staff,
    StaffAbsence,
    StaffHours,
    Studio,
    StudioBreak,
    StudioHours,
    TimeBlock,
)
from app.models.enums import ACTIVE_BOOKING_STATUSES, BookingStatus, SpecialDayKind
from app.services.availability import Hours, Interval, Rules, ServiceSpec, StudioSnapshot

# Multi-day services can end up to this far after the requested window, so occupancy is loaded with margin.
WINDOW_MARGIN = timedelta(days=31)


def studio_rules(studio: Studio) -> Rules:
    return Rules(
        timezone=ZoneInfo(studio.timezone),
        slot_step=timedelta(minutes=studio.slot_step_minutes),
        buffer=timedelta(minutes=studio.buffer_minutes),
        min_lead=timedelta(minutes=studio.min_lead_minutes),
        horizon_days=studio.horizon_days,
        respect_staff_availability=studio.respect_staff_availability,
    )


async def load_service_spec(session: AsyncSession, studio_id: int, service_id: int) -> tuple[Service, ServiceSpec]:
    service = await session.scalar(select(Service).where(Service.studio_id == studio_id, Service.id == service_id))
    if service is None or not service.is_active:
        raise NotFoundError("Услуга не найдена")
    staff_ids = (
        await session.scalars(
            select(Staff.id)
            .join(ServiceStaff, and_(ServiceStaff.staff_id == Staff.id, ServiceStaff.studio_id == Staff.studio_id))
            .where(ServiceStaff.service_id == service.id, Staff.studio_id == studio_id, Staff.is_active.is_(True))
            .order_by(Staff.sort_order, Staff.id)
        )
    ).all()
    spec = ServiceSpec(
        id=service.id,
        duration_minutes=service.duration_minutes,
        duration_days=service.duration_days,
        requires_resource=service.requires_resource,
        requires_staff=service.requires_staff,
        staff_ids=tuple(staff_ids),
    )
    return service, spec


async def load_snapshot(
    session: AsyncSession,
    studio: Studio,
    window_start: datetime,
    window_end: datetime,
    *,
    now: datetime | None = None,
    exclude_booking_id: int | None = None,
) -> StudioSnapshot:
    now = now or datetime.now(UTC)
    sid = studio.id
    snap = StudioSnapshot(rules=studio_rules(studio), weekly_hours={})

    for row in await session.scalars(select(StudioHours).where(StudioHours.studio_id == sid)):
        snap.weekly_hours[row.weekday] = Hours(row.opens_at, row.closes_at) if row.is_open else None
    for row in await session.scalars(select(StudioBreak).where(StudioBreak.studio_id == sid)):
        snap.breaks.setdefault(row.weekday, []).append((row.starts_at, row.ends_at))

    first_day = (window_start - timedelta(days=1)).astimezone(snap.tz).date()
    last_day = (window_end + WINDOW_MARGIN).astimezone(snap.tz).date()
    for row in await session.scalars(
        select(SpecialDay).where(SpecialDay.studio_id == sid, SpecialDay.day.between(first_day, last_day))
    ):
        snap.special_days[row.day] = (
            None if row.kind == SpecialDayKind.CLOSED else Hours(row.opens_at, row.closes_at)  # type: ignore[arg-type]
        )

    snap.resource_ids = list(
        (
            await session.scalars(
                select(Resource.id)
                .where(Resource.studio_id == sid, Resource.is_active.is_(True))
                .order_by(Resource.sort_order, Resource.id)
            )
        ).all()
    )

    staff_hours: dict[int, dict[int, Hours | None]] = defaultdict(dict)
    for row in await session.scalars(
        select(StaffHours)
        .join(Staff, Staff.id == StaffHours.staff_id)
        .where(StaffHours.studio_id == sid, Staff.is_active.is_(True))
    ):
        staff_hours[row.staff_id][row.weekday] = Hours(row.starts_at, row.ends_at) if row.is_working else None
    snap.staff_hours = dict(staff_hours)

    for row in await session.scalars(
        select(StaffAbsence).where(
            StaffAbsence.studio_id == sid, StaffAbsence.ends_on >= first_day, StaffAbsence.starts_on <= last_day
        )
    ):
        snap.staff_absences.setdefault(row.staff_id, []).append((row.starts_on, row.ends_on))

    range_start, range_end = window_start - WINDOW_MARGIN, window_end + WINDOW_MARGIN
    for row in await session.scalars(
        select(TimeBlock).where(
            TimeBlock.studio_id == sid, TimeBlock.ends_at > range_start, TimeBlock.starts_at < range_end
        )
    ):
        block = Interval(row.starts_at, row.ends_at)
        if row.resource_id is not None:
            snap.resource_blocks.setdefault(row.resource_id, []).append(block)
        elif row.staff_id is not None:
            snap.staff_blocks.setdefault(row.staff_id, []).append(block)
        else:
            snap.studio_blocks.append(block)

    busy_query = select(
        Booking.id, Booking.resource_id, Booking.staff_id, Booking.starts_at, Booking.occupied_until
    ).where(
        Booking.studio_id == sid,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        # Holds that already expired no longer occupy anything.
        or_(Booking.status != BookingStatus.HOLD, Booking.hold_expires_at > now),
        Booking.occupied_until > range_start,
        Booking.starts_at < range_end,
    )
    if exclude_booking_id is not None:
        busy_query = busy_query.where(Booking.id != exclude_booking_id)
    for _, resource_id, staff_id, starts_at, occupied_until in (await session.execute(busy_query)).all():
        interval = Interval(starts_at, occupied_until)
        if resource_id is not None:
            snap.resource_busy.setdefault(resource_id, []).append(interval)
        if staff_id is not None:
            snap.staff_busy.setdefault(staff_id, []).append(interval)
    return snap
