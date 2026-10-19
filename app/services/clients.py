"""Client lookup and creation inside one studio."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.phone import InvalidPhoneError, normalize_ru_phone
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
    telegram_verified: bool = False,
) -> Client:
    """Find the client by phone (normalized) or create one.

    An existing client's name is never overwritten by a new request: the name given with a request is
    stored on the booking (`contact_name`), so typing someone else's phone cannot rename their card.

    The Telegram account is linked only when that cannot hand someone else's card over: a typed phone links
    a brand-new card and only an account no other card uses; a phone confirmed by Telegram
    (`telegram_verified`: the owner shared their own contact) may take over the card.
    """
    client = await session.scalar(select(Client).where(Client.studio_id == studio_id, Client.phone == phone))
    created = client is None
    if client is None:
        client = Client(studio_id=studio_id, phone=phone, full_name=name, tags=[], reminders_enabled=True)
        session.add(client)
    if consent_at is not None:
        client.consent_at = consent_at
        client.consent_version = CONSENT_VERSION
    if telegram_user_id is not None and client.telegram_user_id != telegram_user_id:
        if telegram_verified:
            await link_telegram(
                session, client, user_id=telegram_user_id, chat_id=telegram_chat_id, username=telegram_username
            )
        elif created and await telegram_card(session, studio_id, telegram_user_id) is None:
            client.telegram_user_id = telegram_user_id
            client.telegram_chat_id = telegram_chat_id
            client.telegram_username = telegram_username
    await session.flush()
    return client


async def telegram_card(session: AsyncSession, studio_id: int, telegram_user_id: int) -> Client | None:
    return await session.scalar(
        select(Client).where(Client.studio_id == studio_id, Client.telegram_user_id == telegram_user_id)
    )


async def link_telegram(
    session: AsyncSession, client: Client, *, user_id: int, chat_id: int | None, username: str | None
) -> None:
    """Binds the account to this card. An account belongs to one card per studio, so a previous card loses it."""
    await session.flush()  # a new card needs its id
    await session.execute(
        update(Client)
        .where(Client.studio_id == client.studio_id, Client.telegram_user_id == user_id, Client.id != client.id)
        .values(telegram_user_id=None, telegram_chat_id=None, telegram_username=None)
    )
    client.telegram_user_id, client.telegram_chat_id, client.telegram_username = user_id, chat_id, username


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


async def create_client(
    session: AsyncSession,
    studio_id: int,
    *,
    full_name: str,
    phone: str,
    vehicle: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> Client:
    """A client card added by the studio (e.g. after a phone call). The phone must be new for this studio."""
    try:
        phone = normalize_ru_phone(phone)
    except InvalidPhoneError as exc:
        raise ValidationFailedError(details=[{"field": "phone", "message": str(exc)}]) from exc
    name = " ".join(full_name.split())
    if not name:
        raise ValidationFailedError(details=[{"field": "full_name", "message": "Укажите имя"}])
    existing = await session.scalar(select(Client).where(Client.studio_id == studio_id, Client.phone == phone))
    if existing is not None:
        raise ConflictError(
            "Клиент с этим телефоном уже есть", code="client_exists", details={"client_id": existing.id}
        )
    client = Client(
        studio_id=studio_id,
        phone=phone,
        full_name=name,
        notes=(notes or "").strip() or None,
        tags=_clean_tags(tags),
        reminders_enabled=True,
    )
    session.add(client)
    await session.flush()
    if vehicle and vehicle.strip():
        await remember_vehicle(session, studio_id=studio_id, client_id=client.id, description=" ".join(vehicle.split()))
    await session.commit()
    return client


def _clean_tags(tags: list[str] | None) -> list[str]:
    cleaned = [" ".join(t.split())[:40] for t in tags or [] if t and t.strip()]
    return list(dict.fromkeys(cleaned))[:12]


async def update_client(session: AsyncSession, studio_id: int, client_id: int, **changes: object) -> Client:
    client = await session.scalar(select(Client).where(Client.studio_id == studio_id, Client.id == client_id))
    if client is None:
        raise NotFoundError("Клиент не найден")
    for field in ("full_name", "tags", "reminders_enabled"):
        if field in changes and changes[field] is not None:
            setattr(client, field, changes[field])
    if "notes" in changes:  # an empty note clears it
        client.notes = str(changes["notes"] or "").strip() or None
    vehicle = changes.get("add_vehicle")
    if isinstance(vehicle, str) and vehicle.strip():
        await remember_vehicle(session, studio_id=studio_id, client_id=client.id, description=" ".join(vehicle.split()))
    await session.commit()
    return client
