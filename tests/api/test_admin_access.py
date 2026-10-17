"""Roles, studio isolation and the booking workflow through the panel API."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service, Staff, Studio
from app.models.enums import Role
from tests.api.conftest import first_free_slot, login


def admin_url(studio: Studio, path: str = "") -> str:
    return f"/api/v1/admin/studios/{studio.id}{path}"


async def ids(session: AsyncSession, studio: Studio) -> tuple[int, int]:
    service = await session.scalar(
        select(Service.id).where(Service.studio_id == studio.id, Service.slug == "light-polish")
    )
    staff = await session.scalar(select(Staff.id).where(Staff.studio_id == studio.id, Staff.short_name == "Андрей К."))
    return service, staff


async def create(client: httpx.AsyncClient, studio: Studio, service: int, start: str, **extra) -> httpx.Response:
    payload = {"service_id": service, "starts_at": start, "contact_name": "Ольга", "phone": "89135017329", **extra}
    return await client.post(admin_url(studio, "/bookings"), json=payload)


async def test_panel_requires_login(client: httpx.AsyncClient, studio: Studio) -> None:
    response = await client.get(admin_url(studio, "/settings"))
    assert response.status_code == 401


async def test_other_studios_are_invisible(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, other_studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await make_user("owner@other.test", other_studio)
    await login(client, "owner@other.test")
    service, _ = await ids(session, other_studio)
    start = await first_free_slot(client, "other-studio", service)
    foreign = (await create(client, other_studio, service, start)).json()

    client.cookies.clear()
    await login(client, "owner@velox.test")
    assert (await client.get(admin_url(other_studio, "/settings"))).status_code == 404
    assert (await client.get(admin_url(other_studio, "/clients"))).status_code == 404
    # A booking id from the other studio under our own studio path does not exist either.
    assert (await client.get(admin_url(studio, f"/bookings/{foreign['id']}"))).status_code == 404
    assert (
        await client.post(admin_url(studio, f"/bookings/{foreign['id']}/status"), json={"status": "cancelled"})
    ).status_code == 404
    assert (await client.get(admin_url(studio, f"/clients/{foreign['client_id']}"))).status_code == 404


async def test_roles(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    service, andrey = await ids(session, studio)
    await make_user("admin@velox.test", studio, Role.ADMIN)
    await make_user("master@velox.test", studio, Role.MASTER, staff_id=andrey)

    await login(client, "admin@velox.test")
    assert (await client.get(admin_url(studio, "/settings"))).status_code == 200
    assert (await client.patch(admin_url(studio, "/settings"), json={"city": "X"})).status_code == 403  # owner only
    start = await first_free_slot(client, "velox", service, andrey)
    mine = (await create(client, studio, service, start, staff_id=andrey)).json()
    later = await first_free_slot(client, "velox", service)
    someone_else = (await create(client, studio, service, later, staff_id=None)).json()

    client.cookies.clear()
    await login(client, "master@velox.test")
    first, last = sorted([start, later])
    day = {"date_from": first[:10] + "T00:00:00", "date_to": last[:10] + "T23:59:59"}
    listing = await client.get(admin_url(studio, "/bookings"), params=day)
    assert listing.status_code == 200, listing.text
    visible = {row["id"] for row in listing.json()}
    assert mine["id"] in visible
    if someone_else["staff_id"] != andrey:
        assert someone_else["id"] not in visible
    assert (await client.get(admin_url(studio, "/clients"))).status_code == 403
    assert (
        await client.post(admin_url(studio, f"/bookings/{mine['id']}/status"), json={"status": "done"})
    ).status_code == 403


async def test_booking_workflow_from_the_panel(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    service, andrey = await ids(session, studio)
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    start = await first_free_slot(client, "velox", service, andrey)

    created = await create(client, studio, service, start, staff_id=andrey, internal_note="Светлая кожа")
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["status"] == "confirmed" and booking["source"] == "admin"
    assert [e["kind"] for e in booking["events"]] == ["created"]

    url = admin_url(studio, f"/bookings/{booking['id']}")
    patched = await client.patch(url, json={"client_comment": "Пятно на заднем сиденье", "version": booking["version"]})
    assert patched.status_code == 200
    stale = await client.patch(url, json={"internal_note": "x", "version": booking["version"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_booking"

    done = await client.post(f"{url}/status", json={"status": "done"})
    assert done.status_code == 200 and done.json()["status"] == "done"
    invalid = await client.post(f"{url}/status", json={"status": "new"})
    assert invalid.status_code == 409 and invalid.json()["error"]["code"] == "invalid_status_transition"

    clients = (await client.get(admin_url(studio, "/clients"), params={"q": "501"})).json()
    assert clients["total"] == 1 and clients["items"][0]["visits"] == 1
    card = (await client.get(admin_url(studio, f"/clients/{booking['client_id']}"))).json()
    assert card["history"][0]["status"] == "done"
    updated = await client.patch(
        admin_url(studio, f"/clients/{booking['client_id']}"), json={"tags": ["Постоянный", " Постоянный "]}
    )
    assert updated.json()["tags"] == ["Постоянный"]


async def test_settings_validation_and_clearing(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    url = admin_url(studio, "/settings")
    ok = await client.patch(
        url, json={"phone": "8 (913) 000-00-01", "telegram_bot_username": "@velox_bot", "inn": "7701234567"}
    )
    assert ok.status_code == 200
    assert ok.json()["phone"] == "+79130000001" and ok.json()["telegram_bot_username"] == "velox_bot"
    bad = await client.patch(url, json={"route_url": "javascript:alert(1)", "slot_step_minutes": 45})
    assert bad.status_code == 422
    cleared = await client.patch(url, json={"phone": ""})
    assert cleared.json()["phone"] is None
    public = (await client.get("/api/v1/public/studios/velox")).json()
    assert "phone" not in public and public["telegram_bot_username"] == "velox_bot"
