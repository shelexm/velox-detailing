"""The single booking service used by the site, the admin panel and the Telegram bot.

Race protection works on two levels:
1. Every change that occupies time takes a row lock on the studio (`SELECT ... FOR UPDATE`), so allocation of
   boxes and masters inside one studio is serialized and always computed from committed data.
2. PostgreSQL EXCLUDE constraints reject overlapping active bookings of one master or one box, even if a code
   path ever skipped the lock. Such a violation is reported as "slot taken" (HTTP 409), never as a 500.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.phone import InvalidPhoneError, normalize_ru_phone
from app.models import Booking, BookingEvent, Service, Staff, Studio
from app.models.enums import (
    ACTIVE_BOOKING_STATUSES,
    ActorType,
    BookingSource,
    BookingStatus,
    StaffSelection,
)
from app.services import outbox
from app.services.availability import assign, nearest_available, on_grid
from app.services.clients import get_or_create_client, remember_vehicle
from app.services.snapshot import load_service_spec, load_snapshot

EXCLUSION_VIOLATION = "23P01"
ONLINE_SOURCES = (BookingSource.SITE, BookingSource.TELEGRAM)

TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.HOLD: frozenset({BookingStatus.NEW, BookingStatus.CANCELLED, BookingStatus.EXPIRED}),
    BookingStatus.NEW: frozenset({BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.DONE}),
    BookingStatus.CONFIRMED: frozenset(
        {BookingStatus.NEW, BookingStatus.DONE, BookingStatus.NO_SHOW, BookingStatus.CANCELLED}
    ),
    # Corrections of a mistaken final status by the studio.
    BookingStatus.DONE: frozenset({BookingStatus.CONFIRMED}),
    BookingStatus.NO_SHOW: frozenset({BookingStatus.CONFIRMED}),
    BookingStatus.CANCELLED: frozenset({BookingStatus.NEW}),
    BookingStatus.EXPIRED: frozenset(),
}


class SlotUnavailableError(ConflictError):
    code = "slot_taken"
    message = "Это время уже занято. Выберите другое"


class InvalidTransitionError(ConflictError):
    code = "invalid_status_transition"
    message = "Такое изменение статуса недоступно"


class DeadlinePassedError(ConflictError):
    code = "deadline_passed"
    message = "Изменить запись онлайн уже нельзя. Позвоните в студию"


class StaleBookingError(ConflictError):
    code = "stale_booking"
    message = "Запись изменили в другом окне. Обновите страницу"


class HoldExpiredError(ConflictError):
    code = "hold_expired"
    message = "Время удержания истекло. Выберите время заново"


@dataclass(frozen=True)
class Actor:
    type: ActorType
    user_id: int | None = None

    @classmethod
    def system(cls) -> Actor:
        return cls(ActorType.SYSTEM)


@dataclass
class BookingInput:
    service_id: int
    starts_at: datetime
    contact_name: str
    phone: str
    source: BookingSource
    staff_id: int | None = None
    vehicle: str | None = None
    comment: str | None = None
    consent: bool = False
    status: BookingStatus = BookingStatus.NEW
    internal_note: str | None = None
    telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    telegram_username: str | None = None
    telegram_verified: bool = False  # the phone came from the owner's own Telegram contact


@dataclass
class CreatedBooking:
    booking: Booking
    manage_token: str | None


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_exclusion_violation(exc: IntegrityError) -> bool:
    for candidate in (exc.orig, getattr(exc.orig, "__cause__", None)):
        if getattr(candidate, "sqlstate", None) == EXCLUSION_VIOLATION:
            return True
    return "ex_bookings_" in str(exc.orig)


async def _lock_studio(session: AsyncSession, studio_id: int) -> Studio:
    # populate_existing: the request may have loaded the studio before the lock; its counter must be re-read.
    studio = await session.scalar(
        select(Studio).where(Studio.id == studio_id).with_for_update().execution_options(populate_existing=True)
    )
    if studio is None:
        raise NotFoundError("Студия не найдена")
    return studio


async def _expire_holds(session: AsyncSession, studio_id: int, now: datetime) -> None:
    await session.execute(
        update(Booking)
        .where(Booking.studio_id == studio_id, Booking.status == BookingStatus.HOLD, Booking.hold_expires_at <= now)
        .values(status=BookingStatus.EXPIRED, version=Booking.version + 1)
        .execution_options(synchronize_session=False)
    )


async def _get_booking(session: AsyncSession, studio_id: int, booking_id: int, *, lock: bool = True) -> Booking:
    query = select(Booking).where(Booking.studio_id == studio_id, Booking.id == booking_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    booking = await session.scalar(query)
    if booking is None:
        raise NotFoundError("Запись не найдена")
    return booking


def _clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value[:limit] or None


def _validate_contact(data: BookingInput) -> tuple[str, str]:
    errors = []
    name = _clean_text(data.contact_name, 120)
    if not name:
        errors.append({"field": "contact_name", "message": "Укажите имя"})
    phone = ""
    try:
        phone = normalize_ru_phone(data.phone)
    except InvalidPhoneError as exc:
        errors.append({"field": "phone", "message": str(exc)})
    if data.source in ONLINE_SOURCES and not data.consent:
        errors.append({"field": "consent", "message": "Нужно согласие на обработку персональных данных"})
    if errors:
        raise ValidationFailedError(details=errors)
    return name or "", phone


async def _record(
    session: AsyncSession,
    booking: Booking,
    kind: str,
    actor: Actor,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    data: dict | None = None,
) -> None:
    session.add(
        BookingEvent(
            studio_id=booking.studio_id,
            booking_id=booking.id,
            kind=kind,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor.type,
            actor_user_id=actor.user_id,
            data=data or {},
        )
    )


async def _flush_or_conflict(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if _is_exclusion_violation(exc):
            raise SlotUnavailableError() from exc
        raise


async def _check_staff_choice(session: AsyncSession, service: Service, staff_id: int | None, online: bool) -> None:
    if staff_id is None or not online:
        return
    if service.staff_selection != StaffSelection.CLIENT:
        raise ValidationFailedError("Для этой услуги мастера назначает студия")
    selectable = await session.scalar(
        select(Staff.client_selectable).where(Staff.id == staff_id, Staff.studio_id == service.studio_id)
    )
    if not selectable:
        raise ValidationFailedError("Этого мастера нельзя выбрать онлайн")


async def _allocate(
    session: AsyncSession,
    studio: Studio,
    service_id: int,
    starts_at: datetime,
    *,
    staff_id: int | None,
    online: bool,
    now: datetime,
    exclude_booking_id: int | None = None,
    prefer_staff_id: int | None = None,
):
    """Find a box and a master for the start time; raise SlotUnavailableError with alternatives otherwise."""
    service, spec = await load_service_spec(session, studio.id, service_id)
    snap = await load_snapshot(session, studio, starts_at, starts_at, now=now, exclude_booking_id=exclude_booking_id)
    assignment = None
    if not online or on_grid(snap, starts_at):
        options = dict(now=now, enforce_window=online, allow_blocked_start=not online)
        if staff_id is None and prefer_staff_id is not None and prefer_staff_id in spec.staff_ids:
            assignment = assign(snap, spec, starts_at, staff_id=prefer_staff_id, **options)
        if assignment is None:
            assignment = assign(snap, spec, starts_at, staff_id=staff_id, **options)
    if assignment is None:
        alternatives = nearest_available(snap, spec, starts_at, now=now, staff_id=staff_id) if online else []
        raise SlotUnavailableError(details={"alternatives": [a.isoformat() for a in alternatives]})
    return service, assignment


async def create_booking(
    session: AsyncSession, studio_id: int, data: BookingInput, actor: Actor, *, now: datetime | None = None
) -> CreatedBooking:
    now = now or utcnow()
    online = data.source in ONLINE_SOURCES
    name, phone = _validate_contact(data)
    if data.status not in (BookingStatus.NEW, BookingStatus.CONFIRMED) or (online and data.status != BookingStatus.NEW):
        raise ValidationFailedError("Недопустимый статус новой записи")

    studio = await _lock_studio(session, studio_id)
    if online and not studio.online_booking_enabled:
        raise ConflictError("Онлайн-запись временно недоступна. Позвоните в студию", code="booking_disabled")
    service = await session.scalar(select(Service).where(Service.studio_id == studio_id, Service.id == data.service_id))
    if service is None or not service.is_active:
        raise NotFoundError("Услуга не найдена")
    if online and not service.online_booking:
        raise ValidationFailedError("Эта услуга доступна только по записи через администратора")
    await _check_staff_choice(session, service, data.staff_id, online)
    await _expire_holds(session, studio_id, now)
    service, assignment = await _allocate(
        session, studio, data.service_id, data.starts_at, staff_id=data.staff_id, online=online, now=now
    )

    client = await get_or_create_client(
        session,
        studio_id=studio_id,
        phone=phone,
        name=name,
        consent_at=now if data.consent else None,
        telegram_user_id=data.telegram_user_id,
        telegram_chat_id=data.telegram_chat_id,
        telegram_username=data.telegram_username,
        telegram_verified=data.telegram_verified,
    )
    vehicle_text = _clean_text(data.vehicle, 120)
    vehicle = (
        await remember_vehicle(session, studio_id=studio_id, client_id=client.id, description=vehicle_text)
        if vehicle_text
        else None
    )

    studio.booking_seq += 1
    manage_token = secrets.token_urlsafe(24) if online else None
    booking = Booking(
        studio_id=studio_id,
        number=studio.booking_seq,
        client_id=client.id,
        vehicle_id=vehicle.id if vehicle else None,
        service_id=service.id,
        staff_id=assignment.staff_id,
        resource_id=assignment.resource_id,
        starts_at=assignment.start,
        ends_at=assignment.end,
        occupied_until=assignment.occupied_until,
        status=data.status,
        source=data.source,
        contact_name=name,
        vehicle_description=vehicle_text,
        client_comment=_clean_text(data.comment, 1000),
        internal_note=_clean_text(data.internal_note, 2000),
        service_name=service.name,
        price_from=service.price_from,
        manage_token_hash=hash_token(manage_token) if manage_token else None,
        created_by_user_id=actor.user_id,
        confirmed_at=now if data.status == BookingStatus.CONFIRMED else None,
    )
    session.add(booking)
    await _flush_or_conflict(session)
    await _record(session, booking, "created", actor, to_status=booking.status, data={"source": data.source})
    # Requests from the site or the bot go to the admins' chat; bookings made by the studio itself do not.
    audiences = (outbox.AUDIENCE_ADMINS, outbox.AUDIENCE_CLIENT) if online else (outbox.AUDIENCE_CLIENT,)
    await outbox.enqueue(session, booking, "booking_created", audiences=audiences)
    await session.commit()
    return CreatedBooking(booking=booking, manage_token=manage_token)


async def _release(session: AsyncSession, studio_id: int, owner: str, now: datetime) -> None:
    # A released hold is a never-completed hold, like an expired one: "cancelled" would show it in the
    # panel calendar as a nameless cancelled booking and inflate the cancellation count.
    await session.execute(
        update(Booking)
        .where(Booking.studio_id == studio_id, Booking.status == BookingStatus.HOLD, Booking.hold_owner == owner)
        .values(status=BookingStatus.EXPIRED, version=Booking.version + 1)
        .execution_options(synchronize_session=False)
    )


async def release_holds(session: AsyncSession, studio_id: int, owner: str) -> None:
    """Free the slot a client holds, e.g. when they step back in the bot dialog."""
    await _release(session, studio_id, owner, utcnow())
    await session.commit()


async def create_hold(
    session: AsyncSession,
    studio_id: int,
    *,
    service_id: int,
    starts_at: datetime,
    owner: str,
    staff_id: int | None = None,
    now: datetime | None = None,
) -> Booking:
    """Hold a slot for `hold_minutes` while the client finishes the bot dialog. One active hold per owner."""
    now = now or utcnow()
    studio = await _lock_studio(session, studio_id)
    if not studio.online_booking_enabled:
        raise ConflictError("Онлайн-запись временно недоступна. Позвоните в студию", code="booking_disabled")
    service = await session.scalar(select(Service).where(Service.studio_id == studio_id, Service.id == service_id))
    if service is None or not service.is_active or not service.online_booking:
        raise NotFoundError("Услуга не найдена")
    await _check_staff_choice(session, service, staff_id, online=True)
    await _expire_holds(session, studio_id, now)
    await _release(session, studio_id, owner, now)
    service, assignment = await _allocate(
        session, studio, service_id, starts_at, staff_id=staff_id, online=True, now=now
    )
    studio.booking_seq += 1
    hold = Booking(
        studio_id=studio_id,
        number=studio.booking_seq,
        service_id=service.id,
        staff_id=assignment.staff_id,
        resource_id=assignment.resource_id,
        starts_at=assignment.start,
        ends_at=assignment.end,
        occupied_until=assignment.occupied_until,
        status=BookingStatus.HOLD,
        source=BookingSource.TELEGRAM,
        hold_expires_at=now + timedelta(minutes=studio.hold_minutes),
        hold_owner=owner,
        service_name=service.name,
        price_from=service.price_from,
    )
    session.add(hold)
    await _flush_or_conflict(session)
    await _record(session, hold, "hold_created", Actor(ActorType.BOT), to_status=BookingStatus.HOLD)
    await session.commit()
    return hold


async def complete_hold(
    session: AsyncSession,
    studio_id: int,
    hold_id: int,
    *,
    owner: str,
    data: BookingInput,
    now: datetime | None = None,
) -> CreatedBooking:
    """Turn a held slot into a new booking once the client has given a name and phone."""
    now = now or utcnow()
    name, phone = _validate_contact(data)
    await _lock_studio(session, studio_id)
    hold = await _get_booking(session, studio_id, hold_id)
    if hold.hold_owner != owner or hold.status not in (BookingStatus.HOLD, BookingStatus.EXPIRED):
        raise NotFoundError("Запись не найдена")
    if hold.status == BookingStatus.EXPIRED or hold.hold_expires_at is None or hold.hold_expires_at <= now:
        raise HoldExpiredError()

    client = await get_or_create_client(
        session,
        studio_id=studio_id,
        phone=phone,
        name=name,
        consent_at=now if data.consent else None,
        telegram_user_id=data.telegram_user_id,
        telegram_chat_id=data.telegram_chat_id,
        telegram_username=data.telegram_username,
        telegram_verified=data.telegram_verified,
    )
    vehicle_text = _clean_text(data.vehicle, 120)
    if vehicle_text:
        vehicle = await remember_vehicle(session, studio_id=studio_id, client_id=client.id, description=vehicle_text)
        hold.vehicle_id = vehicle.id
    manage_token = secrets.token_urlsafe(24)
    hold.client_id = client.id
    hold.contact_name = name
    hold.vehicle_description = vehicle_text
    hold.client_comment = _clean_text(data.comment, 1000)
    hold.status = BookingStatus.NEW
    hold.hold_expires_at = None
    hold.manage_token_hash = hash_token(manage_token)
    await _flush_or_conflict(session)
    await _record(
        session,
        hold,
        "created",
        Actor(ActorType.CLIENT),
        from_status=BookingStatus.HOLD,
        to_status=BookingStatus.NEW,
        data={"source": BookingSource.TELEGRAM},
    )
    # The client is in the bot chat right now and gets the answer there; only the admins are notified.
    await outbox.enqueue(session, hold, "booking_created", audiences=(outbox.AUDIENCE_ADMINS,))
    await session.commit()
    return CreatedBooking(booking=hold, manage_token=manage_token)


async def change_status(
    session: AsyncSession,
    studio_id: int,
    booking_id: int,
    new_status: BookingStatus,
    actor: Actor,
    *,
    reason: str | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> Booking:
    now = now or utcnow()
    reactivating = new_status in ACTIVE_BOOKING_STATUSES
    if reactivating:
        await _lock_studio(session, studio_id)
    booking = await _get_booking(session, studio_id, booking_id)
    if expected_version is not None and booking.version != expected_version:
        raise StaleBookingError()
    old_status = booking.status
    if new_status == old_status:
        return booking
    if new_status not in TRANSITIONS[old_status]:
        raise InvalidTransitionError()

    booking.status = new_status
    if new_status == BookingStatus.CONFIRMED and booking.confirmed_at is None:
        booking.confirmed_at = now
    if new_status == BookingStatus.CANCELLED:
        booking.cancelled_at = now
        booking.cancel_reason = _clean_text(reason, 300)
    if old_status == BookingStatus.CANCELLED:
        booking.cancelled_at = None
        booking.cancel_reason = None
    await _flush_or_conflict(session)
    await _record(session, booking, "status_changed", actor, from_status=old_status, to_status=new_status)

    by_client = actor.type in (ActorType.CLIENT, ActorType.BOT)
    if new_status == BookingStatus.CONFIRMED:
        await outbox.enqueue(session, booking, "booking_confirmed", audiences=(outbox.AUDIENCE_CLIENT,))
    elif new_status == BookingStatus.CANCELLED:
        audience = outbox.AUDIENCE_ADMINS if by_client else outbox.AUDIENCE_CLIENT
        await outbox.enqueue(session, booking, "booking_cancelled", audiences=(audience,))
    await session.commit()
    return booking


async def cancel_by_client(
    session: AsyncSession, studio_id: int, booking_id: int, *, actor: Actor, now: datetime | None = None
) -> Booking:
    now = now or utcnow()
    booking = await _get_booking(session, studio_id, booking_id, lock=False)
    studio = await session.get(Studio, studio_id)
    if booking.status not in (BookingStatus.NEW, BookingStatus.CONFIRMED):
        raise InvalidTransitionError("Эту запись уже нельзя отменить")
    if booking.starts_at - now < timedelta(hours=studio.cancel_deadline_hours):  # type: ignore[union-attr]
        raise DeadlinePassedError()
    return await change_status(session, studio_id, booking_id, BookingStatus.CANCELLED, actor, reason="client", now=now)


async def reschedule(
    session: AsyncSession,
    studio_id: int,
    booking_id: int,
    *,
    starts_at: datetime,
    actor: Actor,
    service_id: int | None = None,
    staff_id: int | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> Booking:
    """Move a booking (and optionally change its service or master). Clients go through the online rules."""
    now = now or utcnow()
    by_client = actor.type in (ActorType.CLIENT, ActorType.BOT)
    studio = await _lock_studio(session, studio_id)
    booking = await _get_booking(session, studio_id, booking_id)
    if expected_version is not None and booking.version != expected_version:
        raise StaleBookingError()
    if booking.status not in (BookingStatus.NEW, BookingStatus.CONFIRMED):
        raise InvalidTransitionError("Перенести можно только новую или подтверждённую запись")
    if by_client and booking.starts_at - now < timedelta(hours=studio.cancel_deadline_hours):
        raise DeadlinePassedError()

    target_service_id = service_id or booking.service_id
    service, assignment = await _allocate(
        session,
        studio,
        target_service_id,
        starts_at,
        staff_id=staff_id,
        online=by_client,
        now=now,
        exclude_booking_id=booking.id,
        prefer_staff_id=booking.staff_id,
    )
    previous = {
        "starts_at": booking.starts_at.isoformat(),
        "service_id": booking.service_id,
        "staff_id": booking.staff_id,
    }
    booking.service_id = service.id
    booking.service_name = service.name
    booking.price_from = service.price_from
    booking.staff_id = assignment.staff_id
    booking.resource_id = assignment.resource_id
    booking.starts_at = assignment.start
    booking.ends_at = assignment.end
    booking.occupied_until = assignment.occupied_until
    old_status = booking.status
    if by_client and booking.status == BookingStatus.CONFIRMED:
        booking.status = BookingStatus.NEW  # the studio confirms the new time again
    try:
        await _flush_or_conflict(session)
    except StaleDataError as exc:
        await session.rollback()
        raise StaleBookingError() from exc
    await _record(
        session,
        booking,
        "rescheduled",
        actor,
        from_status=old_status,
        to_status=booking.status,
        data={"previous": previous},
    )
    audience = outbox.AUDIENCE_ADMINS if by_client else outbox.AUDIENCE_CLIENT
    await outbox.enqueue(
        session, booking, "booking_rescheduled", audiences=(audience,), extra={"previous_start": previous["starts_at"]}
    )
    await session.commit()
    return booking


async def update_details(
    session: AsyncSession,
    studio_id: int,
    booking_id: int,
    actor: Actor,
    *,
    contact_name: str | None = None,
    vehicle: str | None = None,
    client_comment: str | None = None,
    internal_note: str | None = None,
    expected_version: int | None = None,
) -> Booking:
    booking = await _get_booking(session, studio_id, booking_id)
    if expected_version is not None and booking.version != expected_version:
        raise StaleBookingError()
    changed = {}
    for field, value, limit in (
        ("contact_name", contact_name, 120),
        ("vehicle_description", vehicle, 120),
        ("client_comment", client_comment, 1000),
        ("internal_note", internal_note, 2000),
    ):
        if value is not None and getattr(booking, field) != (cleaned := _clean_text(value, limit)):
            setattr(booking, field, cleaned)
            changed[field] = True
    if changed:
        await session.flush()
        await _record(session, booking, "updated", actor, data={"fields": sorted(changed)})
    await session.commit()
    return booking


async def find_by_manage_token(session: AsyncSession, studio_id: int, token: str) -> Booking:
    booking = await session.scalar(
        select(Booking).where(Booking.studio_id == studio_id, Booking.manage_token_hash == hash_token(token))
    )
    if booking is None:
        raise NotFoundError("Запись не найдена")
    return booking
