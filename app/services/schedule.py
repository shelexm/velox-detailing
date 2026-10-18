"""Studio hours, breaks, special days and time blocks from the panel."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Booking, Resource, SpecialDay, Staff, StaffHours, Studio, StudioBreak, StudioHours, TimeBlock
from app.models.enums import ACTIVE_BOOKING_STATUSES
from app.schemas.schedule import SpecialDayIn, StudioDayIn, TimeBlockIn


async def set_week(session: AsyncSession, studio_id: int, days: list[StudioDayIn]) -> int:
    """Saves the weekly hours and breaks. Returns how many masters' shifts now fall outside the studio hours
    (online booking already ignores those parts; the panel asks to fix them)."""
    existing = {
        row.weekday: row for row in await session.scalars(select(StudioHours).where(StudioHours.studio_id == studio_id))
    }
    for day in days:
        row = existing.get(day.weekday)
        if row is None:
            row = StudioHours(studio_id=studio_id, weekday=day.weekday)
            session.add(row)
        row.is_open = day.is_open
        if day.opens_at and day.closes_at:
            row.opens_at, row.closes_at = day.opens_at, day.closes_at
        elif row.opens_at is None:
            raise ValidationFailedError(details=[{"field": f"days.{day.weekday}", "message": "Укажите часы"}])
    await session.execute(delete(StudioBreak).where(StudioBreak.studio_id == studio_id))
    for day in days:
        if day.is_open:
            session.add_all(
                StudioBreak(studio_id=studio_id, weekday=day.weekday, starts_at=b.starts_at, ends_at=b.ends_at)
                for b in day.breaks
            )
    await session.flush()

    outside = 0
    by_day = {d.weekday: d for d in days}
    for shift in await session.scalars(
        select(StaffHours)
        .join(Staff, Staff.id == StaffHours.staff_id)
        .where(StaffHours.studio_id == studio_id, StaffHours.is_working.is_(True), Staff.is_active.is_(True))
    ):
        day = by_day[shift.weekday]
        if not day.is_open or shift.starts_at < day.opens_at or shift.ends_at > day.closes_at:
            outside += 1
    await session.commit()
    return outside


async def save_special_day(session: AsyncSession, studio_id: int, data: SpecialDayIn) -> SpecialDay:
    """One special day per date: saving the same date again replaces it."""
    row = await session.scalar(select(SpecialDay).where(SpecialDay.studio_id == studio_id, SpecialDay.day == data.day))
    if row is None:
        row = SpecialDay(studio_id=studio_id, day=data.day)
        session.add(row)
    row.kind, row.opens_at, row.closes_at, row.note = data.kind, data.opens_at, data.closes_at, data.note
    await session.commit()
    return row


async def delete_special_day(session: AsyncSession, studio_id: int, special_id: int) -> None:
    row = await session.scalar(select(SpecialDay).where(SpecialDay.studio_id == studio_id, SpecialDay.id == special_id))
    if row is None:
        raise NotFoundError("День не найден")
    await session.delete(row)
    await session.commit()


async def add_block(session: AsyncSession, studio: Studio, data: TimeBlockIn) -> tuple[TimeBlock, int]:
    """Returns the block and how many active bookings overlap it (they stay, the panel warns)."""
    resource_id = staff_id = None
    if data.scope == "resource":
        resource_id = await session.scalar(
            select(Resource.id).where(Resource.studio_id == studio.id, Resource.id == data.resource_id)
        )
        if resource_id is None:
            raise ValidationFailedError(details=[{"field": "resource_id", "message": "Бокс не найден"}])
    elif data.scope == "staff":
        staff_id = await session.scalar(select(Staff.id).where(Staff.studio_id == studio.id, Staff.id == data.staff_id))
        if staff_id is None:
            raise ValidationFailedError(details=[{"field": "staff_id", "message": "Мастер не найден"}])
    tz = ZoneInfo(studio.timezone)
    start = datetime.combine(data.day, data.starts_at, tzinfo=tz)
    end = datetime.combine(data.day, data.ends_at, tzinfo=tz)
    block = TimeBlock(
        studio_id=studio.id,
        resource_id=resource_id,
        staff_id=staff_id,
        starts_at=start,
        ends_at=end,
        reason=data.reason,
    )
    session.add(block)
    overlap = select(func.count()).where(
        Booking.studio_id == studio.id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        Booking.starts_at < end,
        Booking.ends_at > start,
    )
    if resource_id is not None:
        overlap = overlap.where(Booking.resource_id == resource_id)
    if staff_id is not None:
        overlap = overlap.where(Booking.staff_id == staff_id)
    clashes = await session.scalar(overlap) or 0
    await session.commit()
    return block, clashes


async def delete_block(session: AsyncSession, studio_id: int, block_id: int) -> None:
    row = await session.scalar(select(TimeBlock).where(TimeBlock.studio_id == studio_id, TimeBlock.id == block_id))
    if row is None:
        raise NotFoundError("Блокировка не найдена")
    await session.delete(row)
    await session.commit()
