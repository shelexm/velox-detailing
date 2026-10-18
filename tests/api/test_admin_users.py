"""Owner screens: settings page, panel access with temporary passwords, last owner protection."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Staff, Studio, StudioMembership, User
from app.models.enums import Role
from tests.api.conftest import PASSWORD, login

HTML = {"Accept": "text/html"}


def fresh_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=client._transport, base_url="http://testserver")


async def test_add_member_and_sign_in(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    owner = await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{studio.id}/users"
    andrey = await session.scalar(select(Staff.id).where(Staff.short_name == "Андрей К."))

    added = await client.post(
        api, json={"email": " Andrey@Velox.TEST ", "full_name": "Андрей", "role": "master", "staff_id": andrey}
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert body["email"] == "andrey@velox.test" and len(body["temporary_password"]) >= 12
    stored = await session.scalar(select(User).where(User.email == "andrey@velox.test"))
    assert body["temporary_password"] not in stored.password_hash  # only the hash is kept

    other = fresh_client(client)
    assert (await login(other, "andrey@velox.test", body["temporary_password"])).status_code == 200
    page = await other.get(f"/admin/{studio.id}/", headers=HTML)
    assert page.status_code == 200 and "Клиентов в базе" not in page.text  # master view
    assert (await other.get(f"/admin/{studio.id}/settings", headers=HTML)).status_code == 403

    assert (await client.post(api, json={"email": "andrey@velox.test", "full_name": "x"})).status_code == 409
    assert (await client.post(api, json={"email": "not-an-email", "full_name": "x"})).status_code == 422

    reset = await client.post(f"{api}/{stored.id}/reset-password")
    assert reset.status_code == 200 and reset.json()["temporary_password"] != body["temporary_password"]
    assert (await other.get("/api/v1/auth/me")).status_code == 401  # signed out by the reset
    await other.aclose()

    promoted = await client.patch(f"{api}/{stored.id}", json={"role": "admin"})
    assert promoted.json() == {"user_id": stored.id, "role": "admin", "staff_id": None}
    assert (await client.delete(f"{api}/{stored.id}")).status_code == 204
    assert await session.scalar(select(StudioMembership).where(StudioMembership.user_id == stored.id)) is None

    # The owner cannot lock themselves out.
    assert (await client.delete(f"{api}/{owner.id}")).status_code == 409
    assert (await client.patch(f"{api}/{owner.id}", json={"role": "admin"})).status_code == 409
    assert (await client.post(f"{api}/{owner.id}/reset-password")).status_code == 422


async def test_existing_account_joins_without_new_password(
    client: httpx.AsyncClient, studio: Studio, other_studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await make_user("shared@velox.test", other_studio)
    await login(client, "owner@velox.test")
    added = await client.post(
        f"/api/v1/admin/studios/{studio.id}/users", json={"email": "shared@velox.test", "full_name": "Общий"}
    )
    assert added.status_code == 201 and added.json()["temporary_password"] is None
    other = fresh_client(client)
    assert (await login(other, "shared@velox.test", PASSWORD)).status_code == 200
    assert (await other.get("/admin", headers=HTML)).status_code == 200  # two studios: picker page
    await other.aclose()


async def test_owner_pages_and_roles(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await make_user("admin@velox.test", studio, role=Role.ADMIN)
    await login(client, "owner@velox.test")
    settings = await client.get(f"/admin/{studio.id}/settings", headers=HTML)
    assert settings.status_code == 200 and "Настройки студии" in settings.text
    users = await client.get(f"/admin/{studio.id}/users", headers=HTML)
    assert users.status_code == 200 and "admin@velox.test" in users.text and "это вы" in users.text

    saved = await client.patch(
        f"/api/v1/admin/studios/{studio.id}/settings", json={"phone": "8 900 123 45 67", "city": "Казань"}
    )
    assert saved.status_code == 200
    site = await client.get("/", headers=HTML)
    assert "+7 900 123-45-67" in site.text and "Казань" in site.text

    admin = fresh_client(client)
    await login(admin, "admin@velox.test")
    assert (await admin.get(f"/admin/{studio.id}/users", headers=HTML)).status_code == 403
    assert (
        await admin.post(f"/api/v1/admin/studios/{studio.id}/users", json={"email": "x@y.zz", "full_name": "x"})
    ).status_code == 403
    await admin.aclose()


async def test_telegram_link_code(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    from app.core import security

    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{studio.id}/telegram"
    issued = await client.post(f"{api}/link-code")
    assert issued.status_code == 200 and issued.json()["command"].startswith("/link ")
    code = issued.json()["code"]
    await session.refresh(studio)
    assert studio.telegram_link_code_hash == security.token_hash(code)  # only the hash is stored
    studio.telegram_admin_chat_id = -100123
    await session.commit()
    assert (await client.delete(f"{api}/admin-chat")).status_code == 204
    await session.refresh(studio)
    assert studio.telegram_admin_chat_id is None and studio.telegram_link_code_hash is None
    page = await client.get(f"/admin/{studio.id}/settings", headers=HTML)
    assert "Получить код привязки" in page.text
