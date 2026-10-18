"""Data the bot shows and the checks it makes. No Telegram objects here, so it is tested against the database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.core.errors import NotFoundError
from app.models import Booking, Client, Service, ServiceGroup, Staff, Studio
from app.models.enums import BookingStatus, StaffSelection
from app.services import queries
from app.web.templating import rub

UPCOMING = (BookingStatus.NEW, BookingStatus.CONFIRMED)


@dataclass
class MenuItem:
    label: str
    kind: str  # group | service
    id: int


async def studio_by_slug(session: AsyncSession, slug: str) -> Studio:
    studio = await session.scalar(select(Studio).where(Studio.slug == slug))
    if studio is None:
        raise NotFoundError("Студия не найдена")
    return studio


def tz(studio: Studio) -> ZoneInfo:
    return ZoneInfo(studio.timezone)


async def online_services(session: AsyncSession, studio_id: int) -> list[Service]:
    return list(
        await session.scalars(
            select(Service)
            .where(Service.studio_id == studio_id, Service.is_active.is_(True), Service.online_booking.is_(True))
            .order_by(Service.sort_order, Service.id)
        )
    )


async def service_menu(session: AsyncSession, studio_id: int) -> list[MenuItem]:
    """Landing directions with online services first (one button each), then standalone services."""
    services = await online_services(session, studio_id)
    groups = {
        g.id: g
        for g in await session.scalars(
            select(ServiceGroup).where(ServiceGroup.studio_id == studio_id, ServiceGroup.is_visible.is_(True))
        )
    }
    items: list[MenuItem] = []
    seen_groups: set[int] = set()
    by_group: dict[int, list[Service]] = {}
    for service in services:
        if service.group_id in groups:
            by_group.setdefault(service.group_id, []).append(service)
    for group in sorted(groups.values(), key=lambda g: g.sort_order):
        members = by_group.get(group.id)
        if not members:
            continue
        seen_groups.add(group.id)
        cheapest = min((s.price_from for s in members if s.price_from is not None), default=None)
        price = f" · {rub(cheapest)}" if cheapest is not None else ""
        if len(members) == 1:
            items.append(MenuItem(f"{group.title}{price}", "service", members[0].id))
        else:
            items.append(MenuItem(f"{group.title}{price}", "group", group.id))
    for service in services:
        if service.group_id not in seen_groups:
            price = f" · {rub(service.price_from)}" if service.price_from is not None else ""
            items.append(MenuItem(f"{service.name}{price}", "service", service.id))
    return items


async def group_variants(session: AsyncSession, studio_id: int, group_id: int) -> tuple[str, list[Service]]:
    group = await session.scalar(
        select(ServiceGroup).where(ServiceGroup.studio_id == studio_id, ServiceGroup.id == group_id)
    )
    if group is None:
        raise NotFoundError("Направление не найдено")
    members = [s for s in await online_services(session, studio_id) if s.group_id == group_id]
    return group.title, members


async def get_service(session: AsyncSession, studio_id: int, service_id: int) -> Service:
    service = await session.scalar(
        select(Service).where(
            Service.studio_id == studio_id,
            Service.id == service_id,
            Service.is_active.is_(True),
            Service.online_booking.is_(True),
        )
    )
    if service is None:
        raise NotFoundError("Услуга недоступна для онлайн-записи")
    return service


def service_summary(service: Service) -> tuple[str, str]:
    """(duration, price) phrases for "Керамика занимает 2–3 дня, ориентир от 45 000 ₽"."""
    return (
        texts.duration_text(service.duration_label, service.duration_minutes, service.duration_days),
        texts.price_text(service.price_from),
    )


async def free_days(
    session: AsyncSession, studio: Studio, service_id: int, *, staff_id: int | None = None, limit: int = 8
) -> list[date]:
    found: list[date] = []
    start = datetime.now(tz(studio)).date()
    for chunk in range(0, studio.horizon_days + 1, 14):
        result = await queries.availability(
            session, studio, service_id=service_id, date_from=start + timedelta(days=chunk), days=14, staff_id=staff_id
        )
        for day in result.days:
            if any(s.available for s in day.slots):
                found.append(day.date)
                if len(found) >= limit:
                    return found
        if not result.days:
            break
    return found


async def free_starts(
    session: AsyncSession, studio: Studio, service_id: int, day: date, *, staff_id: int | None = None
) -> list[datetime]:
    result = await queries.availability(
        session, studio, service_id=service_id, date_from=day, days=1, staff_id=staff_id
    )
    if not result.days or result.days[0].date != day:
        return []
    return [s.start for s in result.days[0].slots if s.available]


async def client_by_telegram(session: AsyncSession, studio_id: int, telegram_user_id: int) -> Client | None:
    return await session.scalar(
        select(Client).where(Client.studio_id == studio_id, Client.telegram_user_id == telegram_user_id)
    )


async def own_booking(session: AsyncSession, studio_id: int, booking_id: int, telegram_user_id: int) -> Booking:
    """A booking of the person writing to the bot; anything else looks like it does not exist."""
    booking = await session.scalar(
        select(Booking)
        .join(Client, and_(Client.id == Booking.client_id, Client.studio_id == studio_id))
        .where(Booking.studio_id == studio_id, Booking.id == booking_id, Client.telegram_user_id == telegram_user_id)
    )
    if booking is None:
        raise NotFoundError("Запись не найдена")
    return booking


async def client_bookings(
    session: AsyncSession, studio_id: int, client_id: int, now: datetime | None = None
) -> tuple[list[Booking], list[Booking]]:
    now = now or datetime.now(UTC)
    rows = list(
        await session.scalars(
            select(Booking)
            .where(Booking.studio_id == studio_id, Booking.client_id == client_id)
            .order_by(Booking.starts_at)
        )
    )
    upcoming = [b for b in rows if b.status in UPCOMING and b.ends_at > now]
    past = [b for b in reversed(rows) if b.status == BookingStatus.DONE][:3]
    return upcoming, past


async def staff_name(session: AsyncSession, studio_id: int, staff_id: int | None) -> str | None:
    if staff_id is None:
        return None
    return await session.scalar(select(Staff.short_name).where(Staff.studio_id == studio_id, Staff.id == staff_id))


async def masters_for(session: AsyncSession, studio_id: int, service_id: int) -> list[tuple[int, str]]:
    from app.models import ServiceStaff

    rows = await session.execute(
        select(Staff.id, Staff.short_name)
        .join(ServiceStaff, and_(ServiceStaff.staff_id == Staff.id, ServiceStaff.studio_id == studio_id))
        .where(Staff.studio_id == studio_id, Staff.is_active.is_(True), ServiceStaff.service_id == service_id)
        .order_by(Staff.sort_order)
    )
    return [(staff_id, name) for staff_id, name in rows.all()]


def picks_master(service: Service) -> bool:
    return service.requires_staff and service.staff_selection == StaffSelection.CLIENT


def address(studio: Studio) -> str | None:
    parts = [p for p in (studio.city, studio.address) if p]
    return ", ".join(parts) or None


async def booking_text(session: AsyncSession, studio: Studio, booking: Booking, title: str, footer: str = "") -> str:
    service = await session.get(Service, booking.service_id)
    duration = texts.duration_text(
        service.duration_label if service else None,
        service.duration_minutes if service else None,
        service.duration_days if service else None,
    )
    return texts.booking_card(
        title=title,
        service=booking.service_name,
        when_text=texts.when(booking.starts_at, tz(studio)),
        vehicle=booking.vehicle_description,
        staff=await staff_name(session, studio.id, booking.staff_id),
        price=booking.price_from,
        duration=duration,
        address=address(studio),
        status=booking.status,
        footer=footer,
    )
