from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE, SESSION_COOKIE
from app.models import Studio, User, UserSession
from app.services.auth import create_or_update_admin
from tests.api.conftest import PASSWORD, login


async def test_login_sets_http_only_session_cookie(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    response = await login(client, "Owner@Velox.test ")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "owner@velox.test"
    assert body["memberships"] == [
        {"studio_id": studio.id, "studio_slug": "velox", "studio_name": studio.name, "role": "owner"}
    ]
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(SESSION_COOKIE))
    csrf_cookie = next(c for c in cookies if c.startswith(CSRF_COOKIE))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_wrong_credentials_get_the_same_answer(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    wrong_password = await login(client, "owner@velox.test", "not the password")
    unknown_email = await login(client, "nobody@velox.test")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"] == unknown_email.json()["error"]
    assert SESSION_COOKIE not in wrong_password.headers.get("set-cookie", "")


async def test_login_attempts_are_limited(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    for _ in range(5):
        assert (await login(client, "owner@velox.test", "wrong")).status_code == 401
    blocked = await login(client, "owner@velox.test")  # even the right password waits now
    assert blocked.status_code == 429


async def test_logout_revokes_the_session(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    stolen = client.cookies[SESSION_COOKIE]
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    client.cookies.set(SESSION_COOKIE, stolen)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_expired_session_is_rejected(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    await session.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await session.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_unsafe_requests_need_csrf_token_and_same_origin(
    client: httpx.AsyncClient, studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    url = f"/api/v1/admin/studios/{studio.id}/settings"
    token = client.headers.pop("X-CSRF-Token")
    missing = await client.patch(url, json={"city": "Тест"})
    assert missing.status_code == 403 and missing.json()["error"]["code"] == "csrf_failed"
    foreign = await client.patch(
        url, json={"city": "Тест"}, headers={"X-CSRF-Token": token, "Origin": "https://evil.example"}
    )
    assert foreign.status_code == 403 and foreign.json()["error"]["code"] == "bad_origin"
    ok = await client.patch(url, json={"city": "Тест"}, headers={"X-CSRF-Token": token, "Origin": "http://testserver"})
    assert ok.status_code == 200


async def test_inactive_user_cannot_log_in(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    user = await make_user("owner@velox.test", studio)
    await session.execute(update(User).where(User.id == user.id).values(is_active=False))
    await session.commit()
    assert (await login(client, "owner@velox.test")).status_code == 401


async def test_bootstrap_admin_command(client: httpx.AsyncClient, session: AsyncSession, studio: Studio) -> None:
    import pytest

    with pytest.raises(ValueError, match="12"):
        await create_or_update_admin(
            session, email="boss@velox.test", full_name="Boss", password="short", studio_slug="velox"
        )
    user, created = await create_or_update_admin(
        session, email="Boss@Velox.test", full_name="Boss", password=PASSWORD, studio_slug="velox"
    )
    assert created and user.email == "boss@velox.test" and user.password_hash.startswith("$argon2id$")
    with pytest.raises(ValueError, match="уже существует"):
        await create_or_update_admin(
            session, email="boss@velox.test", full_name="Boss", password=PASSWORD, studio_slug="velox"
        )
    assert (await login(client, "boss@velox.test")).status_code == 200
