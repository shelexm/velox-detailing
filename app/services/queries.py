"""Read models for the API: every query is filtered by studio_id."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import NotFoundError
from app.core.phone import format_ru_phone
from app.models import (
    Booking,
    BookingEvent,
    Client,
    Resource,
    Service,
    ServiceGroup,
    ServiceStaff,
    Staff,
    Studio,
    User,
    Vehicle,
)
from app.models.enums import BookingStatus, StaffSelection
from app.schemas.booking import (
    AvailabilityOut,
    BookingAdminOut,
    BookingDetailOut,
    BookingEventOut,
    ClientDetailOut,
    ClientListItemOut,
    ClientListOut,
    ClientVisitOut,
    DayOut,
    ServicePublicOut,
    SlotOut,
    StaffPublicOut,
)
from app.schemas.common import initials
from app.services.availability import day_slots
from app.services.snapshot import load_service_spec, load_snapshot


def ensure_aware(moment: datetime, tz: ZoneInfo) -> datetime:
    """A time without an offset is read as studio local time."""
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment


def staff_out(staff: Staff) -> StaffPublicOut:
    return StaffPublicOut(
        id=staff.id,
        short_name=staff.short_name,
        full_name=staff.full_name,
        title=staff.title,
        specializations=list(staff.specializations or []),
        initials=initials(staff.full_name),
    )


async def public_services(session: AsyncSession, studio_id: int, *, online_only: bool = True) -> list[ServicePublicOut]:
    query = (
        select(Service, ServiceGroup)
        .outerjoin(ServiceGroup, and_(ServiceGroup.id == Service.group_id, ServiceGroup.studio_id == studio_id))
        .where(Service.studio_id == studio_id, Service.is_active.is_(True))
        .order_by(Service.sort_order, Service.id)
    )
    if online_only:
        query = query.where(Service.online_booking.is_(True))
    rows = (await session.execute(query)).all()
    staff_rows = (
        await session.execute(
            select(ServiceStaff.service_id, Staff)
            .join(Staff, and_(Staff.id == ServiceStaff.staff_id, Staff.studio_id == studio_id))
            .where(ServiceStaff.studio_id == studio_id, Staff.is_active.is_(True), Staff.client_selectable.is_(True))
            .order_by(Staff.sort_order, Staff.id)
        )
    ).all()
    staff_by_service: dict[int, list[StaffPublicOut]] = {}
    for service_id, staff in staff_rows:
        staff_by_service.setdefault(service_id, []).append(staff_out(staff))
    result = []
    for service, group in rows:
        selectable = service.staff_selection == StaffSelection.CLIENT
        result.append(
            ServicePublicOut(
                id=service.id,
                slug=service.slug,
                kind=service.kind,
                name=service.name,
                short_description=service.short_description,
                price_from=service.price_from,
                duration_label=service.duration_label,
                duration_minutes=service.duration_minutes,
                duration_days=service.duration_days,
                group_slug=group.slug if group else None,
                group_title=group.title if group else None,
                group_short_title=group.short_title if group else None,
                staff_selection=service.staff_selection,
                staff=staff_by_service.get(service.id, []) if selectable else [],
                badge=service.badge,
                note=service.note,
                items=list(service.items or []),
            )
        )
    return result


async def availability(
    session: AsyncSession,
    studio: Studio,
    *,
    service_id: int,
    date_from: date | None,
    days: int,
    staff_id: int | None,
    include_blocked: bool = False,
    now: datetime | None = None,
) -> AvailabilityOut:
    now = now or datetime.now(UTC)
    tz = ZoneInfo(studio.timezone)
    today = now.astimezone(tz).date()
    first = max(date_from or today, today)
    last_allowed = today + timedelta(days=studio.horizon_days)
    _, spec = await load_service_spec(session, studio.id, service_id)
    window_start = datetime.combine(first, datetime.min.time(), tzinfo=tz)
    window_end = window_start + timedelta(days=days)
    snap = await load_snapshot(session, studio, window_start, window_end, now=now)
    out_days = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        if day > last_allowed:
            break
        slots = day_slots(snap, spec, day, now=now, staff_id=staff_id, include_blocked=include_blocked)
        out_days.append(
            DayOut(
                date=day,
                open=snap.opening(day) is not None,
                slots=[
                    SlotOut(
                        start=s.start,
                        end=s.end,
                        available=s.available,
                        free_places=s.free_places,
                        total_places=s.total_places,
                        blocked=s.blocked,
                    )
                    for s in slots
                ],
            )
        )
    return AvailabilityOut(service_id=service_id, timezone=studio.timezone, days=out_days)


def _booking_query(studio_id: int):
    return (
        select(Booking, Client, Staff, Resource)
        .outerjoin(Client, and_(Client.id == Booking.client_id, Client.studio_id == studio_id))
        .outerjoin(Staff, and_(Staff.id == Booking.staff_id, Staff.studio_id == studio_id))
        .outerjoin(Resource, and_(Resource.id == Booking.resource_id, Resource.studio_id == studio_id))
        .where(Booking.studio_id == studio_id)
    )


def _booking_out(booking: Booking, client: Client | None, staff: Staff | None, resource: Resource | None) -> dict:
    return dict(
        id=booking.id,
        number=booking.number,
        status=booking.status,
        source=booking.source,
        service_id=booking.service_id,
        service_name=booking.service_name,
        staff_id=booking.staff_id,
        staff_name=staff.short_name if staff else None,
        resource_id=booking.resource_id,
        resource_name=resource.name if resource else None,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        client_id=booking.client_id,
        client_name=client.full_name if client else None,
        contact_name=booking.contact_name,
        phone=format_ru_phone(client.phone) if client else None,
        telegram_username=client.telegram_username if client else None,
        vehicle=booking.vehicle_description,
        client_comment=booking.client_comment,
        internal_note=booking.internal_note,
        price_from=booking.price_from,
        created_at=booking.created_at,
        version=booking.version,
    )


async def list_bookings(
    session: AsyncSession,
    studio_id: int,
    *,
    date_from: datetime,
    date_to: datetime,
    statuses: list[BookingStatus] | None = None,
    staff_id: int | None = None,
    query: str | None = None,
    limit: int = 500,
) -> list[BookingAdminOut]:
    stmt = _booking_query(studio_id).where(
        Booking.starts_at < date_to, Booking.ends_at > date_from, Booking.status != BookingStatus.EXPIRED
    )
    stmt = stmt.where(Booking.status.in_(statuses)) if statuses else stmt.where(Booking.status != BookingStatus.HOLD)
    if staff_id is not None:
        stmt = stmt.where(Booking.staff_id == staff_id)
    if query:
        like = f"%{query.strip()}%"
        digits = "".join(ch for ch in query if ch.isdigit())
        conditions = [
            Client.full_name.ilike(like),
            Booking.contact_name.ilike(like),
            Booking.vehicle_description.ilike(like),
        ]
        if digits:
            conditions.append(Client.phone.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conditions))
    rows = (await session.execute(stmt.order_by(Booking.starts_at).limit(limit))).all()
    return [BookingAdminOut(**_booking_out(*row)) for row in rows]


async def new_requests(
    session: AsyncSession, studio_id: int, *, staff_id: int | None = None, limit: int = 6
) -> list[BookingAdminOut]:
    """Bookings waiting for the studio's answer, newest first."""
    stmt = _booking_query(studio_id).where(Booking.status == BookingStatus.NEW)
    if staff_id is not None:
        stmt = stmt.where(Booking.staff_id == staff_id)
    rows = (await session.execute(stmt.order_by(Booking.created_at.desc()).limit(limit))).all()
    return [BookingAdminOut(**_booking_out(*row)) for row in rows]


async def booking_detail(
    session: AsyncSession, studio_id: int, booking_id: int, *, staff_id: int | None = None
) -> BookingDetailOut:
    stmt = _booking_query(studio_id).where(Booking.id == booking_id)
    if staff_id is not None:
        stmt = stmt.where(Booking.staff_id == staff_id)
    row = (await session.execute(stmt)).first()
    if row is None:
        raise NotFoundError("Запись не найдена")
    booking, client, _staff, _resource = row
    actor = aliased(User)
    events = (
        await session.execute(
            select(BookingEvent, actor.full_name)
            .outerjoin(actor, actor.id == BookingEvent.actor_user_id)
            .where(BookingEvent.studio_id == studio_id, BookingEvent.booking_id == booking.id)
            .order_by(BookingEvent.created_at, BookingEvent.id)
        )
    ).all()
    visits = 0
    if client is not None:
        visits = await session.scalar(
            select(func.count()).where(
                Booking.studio_id == studio_id, Booking.client_id == client.id, Booking.status == BookingStatus.DONE
            )
        )
    return BookingDetailOut(
        **_booking_out(*row),
        events=[
            BookingEventOut(
                kind=e.kind,
                from_status=e.from_status,
                to_status=e.to_status,
                actor_type=e.actor_type,
                actor_name=name,
                data=e.data,
                created_at=e.created_at,
            )
            for e, name in events
        ],
        client_visits=visits or 0,
    )


SEGMENTS = ("all", "regular", "new", "lapsed")


async def list_clients(
    session: AsyncSession,
    studio_id: int,
    *,
    query: str | None,
    segment: str,
    limit: int,
    offset: int,
    now: datetime | None = None,
) -> ClientListOut:
    now = now or datetime.now(UTC)
    done = and_(Booking.status == BookingStatus.DONE)
    stats = (
        select(
            Booking.client_id.label("client_id"),
            func.count().filter(done).label("visits"),
            func.max(Booking.starts_at).filter(done).label("last_visit"),
            func.min(Booking.starts_at)
            .filter(Booking.status.in_((BookingStatus.NEW, BookingStatus.CONFIRMED)), Booking.starts_at >= now)
            .label("next_booking"),
        )
        .where(Booking.studio_id == studio_id, Booking.client_id.is_not(None))
        .group_by(Booking.client_id)
        .subquery()
    )
    visits = func.coalesce(stats.c.visits, 0)
    base = (
        select(Client, visits, stats.c.last_visit, stats.c.next_booking)
        .outerjoin(stats, stats.c.client_id == Client.id)
        .where(Client.studio_id == studio_id)
    )
    if query:
        like = f"%{query.strip()}%"
        digits = "".join(ch for ch in query if ch.isdigit())
        vehicle_match = (
            select(Vehicle.id)
            .where(Vehicle.studio_id == studio_id, Vehicle.client_id == Client.id, Vehicle.description.ilike(like))
            .exists()
        )
        conditions = [Client.full_name.ilike(like), vehicle_match]
        if digits:
            conditions.append(Client.phone.like(f"%{digits}%"))
        base = base.where(or_(*conditions))

    segment_filters = {
        "regular": visits >= 2,
        "new": Client.created_at >= now - timedelta(days=30),
        "lapsed": and_(stats.c.last_visit.is_not(None), stats.c.last_visit < now - timedelta(days=180)),
    }
    count_row = (
        await session.execute(
            select(
                func.count(),
                func.count(case((segment_filters["regular"], 1))),
                func.count(case((segment_filters["new"], 1))),
                func.count(case((segment_filters["lapsed"], 1))),
            )
            .select_from(Client)
            .outerjoin(stats, stats.c.client_id == Client.id)
            .where(Client.studio_id == studio_id)
        )
    ).one()
    counts = dict(zip(SEGMENTS, count_row, strict=True))
    if segment in segment_filters:
        base = base.where(segment_filters[segment])
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await session.execute(base.order_by(Client.full_name, Client.id).limit(limit).offset(offset))).all()
    vehicles = await _vehicles_by_client(session, studio_id, [row[0].id for row in rows])
    items = [
        ClientListItemOut(
            id=client.id,
            full_name=client.full_name,
            phone=format_ru_phone(client.phone),
            vehicles=vehicles.get(client.id, []),
            visits=visit_count,
            last_visit=last_visit,
            next_booking=next_booking,
            tags=list(client.tags or []),
            created_at=client.created_at,
        )
        for client, visit_count, last_visit, next_booking in rows
    ]
    return ClientListOut(total=total or 0, items=items, counts=counts)


async def _vehicles_by_client(session: AsyncSession, studio_id: int, client_ids: list[int]) -> dict[int, list[str]]:
    if not client_ids:
        return {}
    result: dict[int, list[str]] = {}
    for client_id, description in await session.execute(
        select(Vehicle.client_id, Vehicle.description)
        .where(Vehicle.studio_id == studio_id, Vehicle.client_id.in_(client_ids))
        .order_by(Vehicle.created_at.desc())
    ):
        result.setdefault(client_id, []).append(description)
    return result


async def client_detail(
    session: AsyncSession, studio_id: int, client_id: int, *, now: datetime | None = None
) -> ClientDetailOut:
    now = now or datetime.now(UTC)
    client = await session.scalar(select(Client).where(Client.studio_id == studio_id, Client.id == client_id))
    if client is None:
        raise NotFoundError("Клиент не найден")
    history_rows = (
        await session.execute(
            select(Booking, Staff.short_name)
            .outerjoin(Staff, and_(Staff.id == Booking.staff_id, Staff.studio_id == studio_id))
            .where(Booking.studio_id == studio_id, Booking.client_id == client.id)
            .order_by(Booking.starts_at.desc())
        )
    ).all()
    history = [
        ClientVisitOut(
            booking_id=b.id,
            number=b.number,
            service_name=b.service_name,
            starts_at=b.starts_at,
            status=b.status,
            staff_name=staff_name,
        )
        for b, staff_name in history_rows
    ]
    done = [b for b, _ in history_rows if b.status == BookingStatus.DONE]
    upcoming = [
        b.starts_at
        for b, _ in history_rows
        if b.status in (BookingStatus.NEW, BookingStatus.CONFIRMED) and b.starts_at >= now
    ]
    vehicles = await _vehicles_by_client(session, studio_id, [client.id])
    return ClientDetailOut(
        id=client.id,
        full_name=client.full_name,
        phone=format_ru_phone(client.phone),
        vehicles=vehicles.get(client.id, []),
        visits=len(done),
        last_visit=max((b.starts_at for b in done), default=None),
        next_booking=min(upcoming, default=None),
        tags=list(client.tags or []),
        created_at=client.created_at,
        notes=client.notes,
        telegram_username=client.telegram_username,
        reminders_enabled=client.reminders_enabled,
        consent_at=client.consent_at,
        history=history,
    )
