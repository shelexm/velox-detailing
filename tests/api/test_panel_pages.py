"""Panel pages: sign-in redirects, studio isolation, dashboard and password change."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE
from app.models import Booking, Service, Studio
from app.models.enums import Role
from tests.api.conftest import PASSWORD, first_free_slot, login

HTML = {"Accept": "text/html"}


async def test_pages_require_sign_in(client: httpx.AsyncClient, studio: Studio) -> None:
    page = await client.get("/admin/login", headers=HTML)
    assert page.status_code == 200 and "Вход в панель" in page.text
    assert page.headers["x-robots-tag"] == "noindex, nofollow"

    root = await client.get("/admin", headers=HTML)
    assert root.status_code == 303 and root.headers["location"] == "/admin/login"
    deep = await client.get(f"/admin/{studio.id}/account", headers=HTML)
    assert deep.status_code == 303 and deep.headers["location"] == f"/admin/login?next=/admin/{studio.id}/account"


async def test_sign_in_lands_on_the_studio_dashboard(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    assert (await login(client, "owner@velox.test")).status_code == 200

    root = await client.get("/admin", headers=HTML)
    assert root.status_code == 303 and root.headers["location"] == f"/admin/{studio.id}/"
    # Signed in: the login page sends the user on, but never to another site.
    assert (await client.get("/admin/login?next=//evil.example", headers=HTML)).headers["location"] == "/admin"

    # A booking from the site shows up as a new request on the dashboard.
    service = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    start = await first_free_slot(client, "velox", service)
    created = await client.post(
        "/api/v1/public/studios/velox/bookings",
        json={"service_id": service, "starts_at": start, "name": "Кирилл", "phone": "+79001112233", "consent": True},
    )
    assert created.status_code == 201

    for period in ("week", "month", "quarter"):
        page = await client.get(f"/admin/{studio.id}/?period={period}", headers=HTML)
        assert page.status_code == 200, page.text
        assert "Сегодня в студии" in page.text and "Новые заявки" in page.text
        assert "Кирилл" in page.text and "Лёгкая полировка" in page.text
    assert (await client.get(f"/admin/{studio.id}/more", headers=HTML)).status_code == 200
    assert (await client.get(f"/admin/{studio.id}/account", headers=HTML)).status_code == 200


async def test_other_studio_is_not_found(
    client: httpx.AsyncClient, studio: Studio, other_studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    page = await client.get(f"/admin/{other_studio.id}/", headers=HTML)
    assert page.status_code == 404


async def test_master_sees_only_their_part(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("master@velox.test", studio, role=Role.MASTER)
    await login(client, "master@velox.test")
    page = await client.get(f"/admin/{studio.id}/", headers=HTML)
    assert page.status_code == 200
    assert "Клиентов в базе" not in page.text and f"/admin/{studio.id}/schedule" not in page.text


async def test_change_password(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    other = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # second device
    await login(other, "owner@velox.test")

    wrong = await client.post("/api/v1/auth/password", json={"current_password": "nope", "new_password": "x" * 14})
    assert wrong.status_code == 422 and wrong.json()["error"]["details"][0]["field"] == "current_password"
    weak = await client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["details"][0]["field"] == "new_password"

    new_password = "a much longer new secret"
    ok = await client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": new_password})
    assert ok.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 200  # this device stays signed in
    assert (await other.get("/api/v1/auth/me")).status_code == 401  # the other one is signed out
    await other.aclose()

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")
    assert (await login(fresh, "owner@velox.test", new_password)).status_code == 200
    assert CSRF_COOKIE in fresh.cookies
    await fresh.aclose()
    assert await session.scalar(select(Booking.id)) is None
