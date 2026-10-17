from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE, hash_password
from app.models import Studio, StudioMembership, User
from app.models.enums import Role
from app.seed.content import seed_site_content
from app.seed.run import seed_all

PASSWORD = "correct horse battery"


@pytest.fixture
async def studio(session: AsyncSession) -> Studio:
    return await seed_all(session)


@pytest.fixture
async def site_studio(session: AsyncSession, studio: Studio) -> Studio:
    await seed_site_content(session, studio, media={})
    return studio


@pytest.fixture
async def other_studio(session: AsyncSession) -> Studio:
    return await seed_all(session, "other-studio")


@pytest.fixture
def make_user(session: AsyncSession) -> Callable[..., Awaitable[User]]:
    async def factory(email: str, studio: Studio, role: Role = Role.OWNER, staff_id: int | None = None) -> User:
        user = User(email=email, full_name=email.split("@")[0], password_hash=hash_password(PASSWORD), is_active=True)
        session.add(user)
        await session.flush()
        session.add(StudioMembership(studio_id=studio.id, user_id=user.id, role=role, staff_id=staff_id))
        await session.commit()
        return user

    return factory


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = client.cookies[CSRF_COOKIE]
    return response


async def first_free_slot(client: httpx.AsyncClient, slug: str, service_id: int, staff_id: int | None = None) -> str:
    params = {"service_id": service_id, "days": 14}
    if staff_id:
        params["staff_id"] = staff_id
    response = await client.get(f"/api/v1/public/studios/{slug}/availability", params=params)
    assert response.status_code == 200, response.text
    for day in response.json()["days"]:
        for slot in day["slots"]:
            if slot["available"]:
                return slot["start"]
    raise AssertionError("no free slot in two weeks")
