"""Writing notifications to the transactional outbox (same transaction as the booking change).

The payload holds identifiers only: message texts are rendered at delivery time from current data,
so the outbox does not accumulate personal data.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Client, NotificationOutbox
from app.models.enums import OutboxStatus

AUDIENCE_ADMINS = "admins"
AUDIENCE_CLIENT = "client"


async def enqueue(
    session: AsyncSession,
    booking: Booking,
    event: str,
    *,
    audiences: tuple[str, ...],
    extra: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> list[NotificationOutbox]:
    rows = []
    for audience in audiences:
        if audience == AUDIENCE_CLIENT and not await _client_reachable(session, booking):
            continue
        row = NotificationOutbox(
            studio_id=booking.studio_id,
            booking_id=booking.id,
            event=event,
            audience=audience,
            payload={"booking_id": booking.id, "number": booking.number, **(extra or {})},
            status=OutboxStatus.PENDING,
            attempts=0,
            dedupe_key=f"{dedupe_key}:{audience}" if dedupe_key else None,
        )
        session.add(row)
        rows.append(row)
    return rows


async def _client_reachable(session: AsyncSession, booking: Booking) -> bool:
    if booking.client_id is None:
        return False
    chat_id = await session.scalar(select(Client.telegram_chat_id).where(Client.id == booking.client_id))
    return chat_id is not None
