"""Booking rules and boxes: capacity follows the number of active boxes; the slots screen renders."""

from __future__ import annotations

import re
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Resource, Service, Studio
from app.models.enums import Role
from tests.api.conftest import first_free_slot, login

HTML = {"Accept": "text/html"}


async def _owner(client: httpx.AsyncClient, studio: Studio, make_user) -> str:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    return f"/api/v1/admin/studios/{studio.id}"


async def test_rules(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    api = await _owner(client, studio, make_user)
    saved = await client.patch(
        f"{api}/booking-rules", json={"slot_step_minutes": 30, "buffer_minutes": 20, "horizon_days": 14}
    )
    assert saved.status_code == 200 and saved.json()["slot_step_minutes"] == 30
    assert (await client.patch(f"{api}/booking-rules", json={"slot_step_minutes": 45})).status_code == 422
    assert (await client.patch(f"{api}/booking-rules", json={"horizon_days": 0})).status_code == 422

    wash = await session.scalar(select(Service.id).where(Service.slug == "detailing-wash"))
    response = await client.get(
        "/api/v1/public/studios/velox/availability",
        params={"service_id": wash, "date_from": (date.today() + timedelta(days=7)).isoformat()},
    )
    starts = [s["start"][14:16] for d in response.json()["days"] for s in d["slots"]]
    assert "30" in starts  # half-hour grid now
    far = await client.get(
        "/api/v1/public/studios/velox/availability",
        params={"service_id": wash, "date_from": (date.today() + timedelta(days=20)).isoformat()},
    )
    assert far.json()["days"] == []  # beyond the 14-day horizon


async def test_boxes_are_capacity(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    api = await _owner(client, studio, make_user)
    added = await client.post(f"{api}/resources", json={})
    assert added.status_code == 201 and added.json()["name"] == "Бокс 3"
    renamed = await client.patch(f"{api}/resources/{added.json()['id']}", json={"name": "Малярный бокс"})
    assert renamed.json()["name"] == "Малярный бокс"

    polish = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    start = await first_free_slot(client, "velox", polish)
    slot = next(
        s
        for d in (
            await client.get(
                "/api/v1/public/studios/velox/availability",
                params={"service_id": polish, "date_from": start[:10], "days": 1},
            )
        ).json()["days"]
        for s in d["slots"]
        if s["start"] == start
    )
    assert slot["total_places"] == 3

    box = await session.scalar(select(Resource).where(Resource.id == added.json()["id"]))
    assert (await client.delete(f"{api}/resources/{box.id}")).status_code == 204
    await session.refresh(box)
    assert box.is_active is False
    others = list(
        await session.scalars(select(Resource).where(Resource.studio_id == studio.id, Resource.is_active.is_(True)))
    )
    assert (await client.delete(f"{api}/resources/{others[0].id}")).status_code == 204
    last = await client.delete(f"{api}/resources/{others[1].id}")
    assert last.status_code == 409 and last.json()["error"]["code"] == "last_box"


async def test_slots_screen(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    await _owner(client, studio, make_user)
    page = await client.get(f"/admin/{studio.id}/slots", headers=HTML)
    assert page.status_code == 200, page.text
    assert "Автомобилей в одном слоте" in page.text and "Как это видит клиент" in page.text
    assert re.search(r"свободно \d+ из \d+", page.text)
    polish = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    other = await client.get(f"/admin/{studio.id}/slots?service={polish}&day={date.today().isoformat()}", headers=HTML)
    assert other.status_code == 200


async def test_admins_can_change_rules_masters_cannot(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("master@velox.test", studio, role=Role.MASTER)
    await login(client, "master@velox.test")
    assert (
        await client.patch(f"/api/v1/admin/studios/{studio.id}/booking-rules", json={"buffer_minutes": 0})
    ).status_code == 403
