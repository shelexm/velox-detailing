"""Masters from the panel: profile, weekly hours inside the studio hours, services, absences."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import Booking, Service, ServiceStaff, Staff, StaffAbsence, StaffHours, Studio, StudioHours
from app.models.enums import BookingStatus
from app.schemas.staff import AbsenceIn, DayHoursIn, StaffFields

UPCOMING = (BookingStatus.NEW, BookingStatus.CONFIRMED)
WEEKDAYS = ("понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье")


def short_name(full_name: str) -> str:
    """Андрей Ковалёв -> Андрей К."""
    parts = full_name.split()
    if len(parts) < 2:
        return full_name[:64]
    return f"{parts[0]} {parts[1][0]}."[:64]


async def get_staff(session: AsyncSession, studio_id: int, staff_id: int) -> Staff:
    staff = await session.scalar(select(Staff).where(Staff.studio_id == studio_id, Staff.id == staff_id))
    if staff is None:
        raise NotFoundError("Мастер не найден")
    return staff


def _apply(staff: Staff, data: StaffFields) -> None:
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in ("full_name", "short_name", "client_selectable") and value is None:
            continue
        if field == "specializations" and value is None:
            value = []
        setattr(staff, field, value)


async def create_staff(session: AsyncSession, studio: Studio, data: StaffFields) -> Staff:
    last = await session.scalar(select(func.max(Staff.sort_order)).where(Staff.studio_id == studio.id))
    staff = Staff(
        studio_id=studio.id,
        full_name=data.full_name,
        short_name=data.short_name or short_name(data.full_name or ""),
        specializations=[],
        client_selectable=True,
        is_active=True,
        sort_order=(last or 0) + 1,
    )
    _apply(staff, data)
    session.add(staff)
    await session.flush()
    # Start with the studio's own hours; the panel narrows them down.
    for row in await session.scalars(select(StudioHours).where(StudioHours.studio_id == studio.id)):
        session.add(
            StaffHours(
                studio_id=studio.id,
                staff_id=staff.id,
                weekday=row.weekday,
                is_working=row.is_open,
                starts_at=row.opens_at,
                ends_at=row.closes_at,
            )
        )
    await session.commit()
    return staff


async def update_staff(session: AsyncSession, studio_id: int, staff_id: int, data: StaffFields) -> Staff:
    staff = await get_staff(session, studio_id, staff_id)
    _apply(staff, data)
    await session.commit()
    return staff


async def upcoming_count(session: AsyncSession, studio_id: int, staff_id: int, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return (
        await session.scalar(
            select(func.count()).where(
                Booking.studio_id == studio_id,
                Booking.staff_id == staff_id,
                Booking.status.in_(UPCOMING),
                Booking.ends_at > now,
            )
        )
        or 0
    )


async def retire_staff(session: AsyncSession, studio_id: int, staff_id: int) -> None:
    staff = await get_staff(session, studio_id, staff_id)
    pending = await upcoming_count(session, studio_id, staff_id)
    if pending:
        raise ConflictError(
            f"У мастера {pending} предстоящих записей. Перенесите их на другого мастера",
            code="staff_has_bookings",
            details={"bookings": pending},
        )
    staff.is_active = False
    await session.execute(
        delete(ServiceStaff).where(ServiceStaff.studio_id == studio_id, ServiceStaff.staff_id == staff_id)
    )
    await session.commit()


async def set_hours(session: AsyncSession, studio_id: int, staff_id: int, days: list[DayHoursIn]) -> None:
    """A master's shift must fit into the studio hours of that weekday."""
    await get_staff(session, studio_id, staff_id)
    studio_hours = {
        row.weekday: row for row in await session.scalars(select(StudioHours).where(StudioHours.studio_id == studio_id))
    }
    problems = []
    for day in days:
        if not day.is_working:
            continue
        studio_day = studio_hours.get(day.weekday)
        if studio_day is None or not studio_day.is_open:
            problems.append({"field": f"days.{day.weekday}", "message": f"Студия в {WEEKDAYS[day.weekday]} закрыта"})
        elif day.starts_at < studio_day.opens_at or day.ends_at > studio_day.closes_at:
            window = f"{studio_day.opens_at:%H:%M}–{studio_day.closes_at:%H:%M}"
            problems.append({"field": f"days.{day.weekday}", "message": f"Часы студии в этот день: {window}"})
    if problems:
        raise ValidationFailedError("График мастера не может выходить за часы студии", details=problems)
    existing = {
        row.weekday: row
        for row in await session.scalars(
            select(StaffHours).where(StaffHours.studio_id == studio_id, StaffHours.staff_id == staff_id)
        )
    }
    for day in days:
        row = existing.get(day.weekday)
        if row is None:
            row = StaffHours(studio_id=studio_id, staff_id=staff_id, weekday=day.weekday)
            session.add(row)
        row.is_working = day.is_working
        # Days off keep their last times so switching the day back on restores them.
        row.starts_at = day.starts_at or row.starts_at or time(9)
        row.ends_at = day.ends_at or row.ends_at or time(18)
    await session.commit()


async def set_services(session: AsyncSession, studio_id: int, staff_id: int, service_ids: list[int]) -> None:
    await get_staff(session, studio_id, staff_id)
    wanted = list(dict.fromkeys(service_ids))
    found = set(
        await session.scalars(
            select(Service.id).where(
                Service.studio_id == studio_id, Service.id.in_(wanted), Service.is_active.is_(True)
            )
        )
    )
    if len(found) != len(wanted):
        raise ValidationFailedError(details=[{"field": "ids", "message": "Услуга не найдена"}])
    await session.execute(
        delete(ServiceStaff).where(ServiceStaff.studio_id == studio_id, ServiceStaff.staff_id == staff_id)
    )
    session.add_all(ServiceStaff(studio_id=studio_id, service_id=s, staff_id=staff_id) for s in wanted)
    await session.commit()


async def add_absence(
    session: AsyncSession, studio: Studio, staff_id: int, data: AbsenceIn
) -> tuple[StaffAbsence, int]:
    """Returns the absence and how many existing bookings of the master fall into it."""
    await get_staff(session, studio.id, staff_id)
    absence = StaffAbsence(
        studio_id=studio.id,
        staff_id=staff_id,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        kind=data.kind,
        note=data.note,
    )
    session.add(absence)
    tz = ZoneInfo(studio.timezone)
    start = datetime.combine(data.starts_on, time(0), tzinfo=tz)
    end = datetime.combine(data.ends_on + timedelta(days=1), time(0), tzinfo=tz)
    clashes = (
        await session.scalar(
            select(func.count()).where(
                Booking.studio_id == studio.id,
                Booking.staff_id == staff_id,
                Booking.status.in_(UPCOMING),
                Booking.starts_at < end,
                Booking.ends_at > start,
            )
        )
        or 0
    )
    await session.commit()
    return absence, clashes


async def delete_absence(session: AsyncSession, studio_id: int, staff_id: int, absence_id: int) -> None:
    absence = await session.scalar(
        select(StaffAbsence).where(
            StaffAbsence.studio_id == studio_id, StaffAbsence.staff_id == staff_id, StaffAbsence.id == absence_id
        )
    )
    if absence is None:
        raise NotFoundError("Отсутствие не найдено")
    await session.delete(absence)
    await session.commit()


async def absences(session: AsyncSession, studio_id: int, staff_id: int, today: date) -> list[StaffAbsence]:
    return list(
        await session.scalars(
            select(StaffAbsence)
            .where(
                StaffAbsence.studio_id == studio_id, StaffAbsence.staff_id == staff_id, StaffAbsence.ends_on >= today
            )
            .order_by(StaffAbsence.starts_on)
        )
    )
