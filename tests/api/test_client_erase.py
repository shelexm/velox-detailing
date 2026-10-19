"""Erasing a client's personal data on request: owner only, no active bookings, nothing personal left."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram import hold_owner
from app.models import Booking, BookingEvent, Client, Service, Studio, Vehicle
from app.models.enums import BookingSource, BookingStatus, Role
from app.services.privacy import ERASED_NAME
from tests.api.conftest import first_free_slot, login

HTML = {"Accept": "text/html"}


async def test_owner_erases_client_data(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    polish = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    start = await first_free_slot(client, "velox", polish)
    made = await client.post(
        "/api/v1/public/studios/velox/bookings",
        json={
            "service_id": polish,
            "starts_at": start,
            "name": "Алексей",
            "phone": "+7 913 452-18-07",
            "vehicle": "Audi A6 белая",
            "comment": "Позвоните после 18:00",
            "consent": True,
        },
    )
    assert made.status_code == 201, made.text
    booking = await session.scalar(select(Booking).where(Booking.number == made.json()["number"]))
    client_id, booking_id = booking.client_id, booking.id

    await make_user("owner@velox.test", studio)
    await make_user("admin@velox.test", studio, role=Role.ADMIN)
    url = f"/api/v1/admin/studios/{studio.id}/clients/{client_id}"
    panel = f"/admin/{studio.id}"
    await login(client, "admin@velox.test")
    assert (await client.delete(url)).status_code == 403  # irreversible: the owner decides
    await client.post("/api/v1/auth/logout")
    await login(client, "owner@velox.test")
    page = await client.get(f"{panel}/clients?open={client_id}", headers=HTML)
    assert "Удалить данные клиента" in page.text

    refused = await client.delete(url)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "client_has_active_bookings"

    await session.execute(update(Booking).where(Booking.id == booking_id).values(status=BookingStatus.DONE))
    await session.commit()
    erased = await client.delete(url)
    assert erased.status_code == 200 and erased.json() == {"bookings_anonymized": 1}

    session.expire_all()
    assert await session.get(Client, client_id) is None
    assert await session.scalar(select(Vehicle.id).where(Vehicle.client_id == client_id)) is None
    booking = await session.get(Booking, booking_id)
    assert booking.client_id is None and booking.contact_name == ERASED_NAME and booking.status == BookingStatus.DONE
    assert booking.client_comment is None and booking.vehicle_description is None
    kinds = list(await session.scalars(select(BookingEvent.kind).where(BookingEvent.booking_id == booking.id)))
    assert "personal_data_erased" in kinds
    # Nothing personal is left anywhere in the tables that hold booking data.
    for table in ("bookings", "booking_events", "notification_outbox", "clients", "vehicles"):
        query = f"SELECT coalesce(string_agg(t::text, ' '), '') FROM {table} t"  # noqa: S608 (fixed table names)
        dump = await session.scalar(text(query))
        assert "4521807" not in dump and "Алексей" not in dump and "Позвоните" not in dump and "Audi" not in dump

    # The anonymous visit still shows in the panel and in the statistics.
    assert (await client.get(f"{panel}/bookings/{booking_id}", headers=HTML)).status_code == 200
    assert (await client.get(panel, headers=HTML, follow_redirects=True)).status_code == 200
    assert (await client.delete(url)).status_code == 404


async def test_erase_clears_the_telegram_id_from_released_holds(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    card = Client(studio_id=studio.id, phone="+79130000009", full_name="Тест", telegram_user_id=4242, tags=[])
    session.add(card)
    await session.commit()
    # A released bot hold: no client on the row, but it still names the Telegram account.
    service = await session.scalar(select(Service).where(Service.studio_id == studio.id).limit(1))
    now = datetime.now(UTC)
    ghost = Booking(
        studio_id=studio.id,
        number=999,
        service_id=service.id,
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=1),
        occupied_until=now + timedelta(days=3, hours=1),
        status=BookingStatus.EXPIRED,
        source=BookingSource.TELEGRAM,
        hold_owner=hold_owner(4242),
        hold_expires_at=now,
        service_name=service.name,
        price_from=service.price_from,
    )
    session.add(ghost)
    await session.commit()

    erased = await client.delete(f"/api/v1/admin/studios/{studio.id}/clients/{card.id}")
    assert erased.status_code == 200, erased.text
    await session.refresh(ghost)
    assert ghost.hold_owner is None
