"""Erasing a client's personal data on request (152-FZ): the card goes, past visits stay as anonymous rows.

Kept for statistics: dates, service, price, master, box and statuses of past bookings. Removed: the client
card (name, phone, Telegram ids, notes, tags, consent), their cars, and every free-text field of their
bookings, the event payloads and queued notifications (they may quote the phone or a comment).
Database backups keep the old data until they rotate out (BACKUP_KEEP_DAYS); see docs/security.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import Booking, BookingEvent, Client, NotificationOutbox, Vehicle
from app.models.enums import BookingStatus
from app.services.booking import Actor, utcnow

ERASED_NAME = "Данные клиента удалены"
ACTIVE = (BookingStatus.NEW, BookingStatus.CONFIRMED)


@dataclass(frozen=True)
class Erased:
    bookings: int


async def erase_client(session: AsyncSession, studio_id: int, client_id: int, actor: Actor) -> Erased:
    client = await session.scalar(
        select(Client).where(Client.studio_id == studio_id, Client.id == client_id).with_for_update()
    )
    if client is None:
        raise NotFoundError("Клиент не найден")
    active = await session.scalar(
        select(Booking.id).where(
            Booking.studio_id == studio_id, Booking.client_id == client.id, Booking.status.in_(ACTIVE)
        )
    )
    if active is not None:
        raise ConflictError(
            "У клиента есть активные записи: сначала отмените или завершите их", code="client_has_active_bookings"
        )
    ids = list(
        await session.scalars(select(Booking.id).where(Booking.studio_id == studio_id, Booking.client_id == client.id))
    )
    if ids:
        await session.execute(
            update(Booking)
            .where(Booking.studio_id == studio_id, Booking.id.in_(ids))
            .values(
                client_id=None,
                vehicle_id=None,
                contact_name=ERASED_NAME,
                vehicle_description=None,
                client_comment=None,
                internal_note=None,
                cancel_reason=None,
                manage_token_hash=None,
                hold_owner=None,
                version=Booking.version + 1,
                updated_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        await session.execute(
            update(BookingEvent)
            .where(BookingEvent.studio_id == studio_id, BookingEvent.booking_id.in_(ids))
            .values(data={})
            .execution_options(synchronize_session=False)
        )
        await session.execute(
            delete(NotificationOutbox).where(
                NotificationOutbox.studio_id == studio_id, NotificationOutbox.booking_id.in_(ids)
            )
        )
        session.add_all(
            BookingEvent(
                studio_id=studio_id,
                booking_id=booking_id,
                kind="personal_data_erased",
                actor_type=actor.type,
                actor_user_id=actor.user_id,
                data={},
            )
            for booking_id in ids
        )
    await session.execute(delete(Vehicle).where(Vehicle.studio_id == studio_id, Vehicle.client_id == client.id))
    await session.delete(client)
    await session.commit()
    return Erased(bookings=len(ids))
