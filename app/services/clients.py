"""Client lookup and creation inside one studio."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Vehicle

CONSENT_VERSION = "2026-10"


async def get_or_create_client(
    session: AsyncSession,
    *,
    studio_id: int,
    phone: str,
    name: str,
    consent_at: datetime | None,
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
    telegram_username: str | None = None,
) -> Client:
    """Find the client by phone (normalized) or create one.

    An existing client's name is never overwritten by a new request: the name given with a request is
    stored on the booking (`contact_name`), so typing someone else's phone cannot rename their card.
    """
    client = await session.scalar(select(Client).where(Client.studio_id == studio_id, Client.phone == phone))
    if client is None:
        client = Client(studio_id=studio_id, phone=phone, full_name=name, tags=[], reminders_enabled=True)
        session.add(client)
    if consent_at is not None:
        client.consent_at = consent_at
        client.consent_version = CONSENT_VERSION
    if telegram_user_id is not None and client.telegram_user_id is None:
        client.telegram_user_id = telegram_user_id
        client.telegram_chat_id = telegram_chat_id
        client.telegram_username = telegram_username
    await session.flush()
    return client


async def remember_vehicle(session: AsyncSession, *, studio_id: int, client_id: int, description: str) -> Vehicle:
    vehicle = await session.scalar(
        select(Vehicle).where(
            Vehicle.studio_id == studio_id, Vehicle.client_id == client_id, Vehicle.description == description
        )
    )
    if vehicle is None:
        vehicle = Vehicle(studio_id=studio_id, client_id=client_id, description=description)
        session.add(vehicle)
        await session.flush()
    return vehicle
