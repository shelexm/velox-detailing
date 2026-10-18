"""Schedule API: weekly hours with breaks, special days, time blocks; the effect on online slots."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service, SpecialDay, Studio, StudioBreak
from tests.api.conftest import login

HTML = {"Accept": "text/html"}


def week(**overrides) -> dict:
    days = [
        {
            "weekday": i,
            "is_open": True,
            "opens_at": "09:00",
            "closes_at": "21:00",
            "breaks": [{"starts_at": "13:00", "ends_at": "13:30"}],
        }
        for i in range(7)
    ]
    for key, value in overrides.items():
        days[int(key[1:])] |= value
    return {"days": days}


async def _owner(client: httpx.AsyncClient, studio: Studio, make_user) -> str:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    return f"/api/v1/admin/studios/{studio.id}/schedule"


async def _slots(client: httpx.AsyncClient, service_id: int, day: date) -> list[dict]:
    response = await client.get(
        "/api/v1/public/studios/velox/availability",
        params={"service_id": service_id, "date_from": day.isoformat(), "days": 1},
    )
    return response.json()["days"][0]["slots"]


async def test_weekly_hours_and_breaks(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    api = await _owner(client, studio, make_user)
    saved = await client.put(f"{api}/hours", json=week(d6={"is_open": False, "breaks": []}))
    assert saved.status_code == 200, saved.text
    # Masters work on Sundays in the seed: their shifts now fall outside the studio hours.
    assert saved.json()["staff_shifts_outside"] >= 1
    assert len(list(await session.scalars(select(StudioBreak).where(StudioBreak.studio_id == studio.id)))) == 6

    bad_break = await client.put(f"{api}/hours", json=week(d0={"breaks": [{"starts_at": "08:00", "ends_at": "08:30"}]}))
    assert bad_break.status_code == 422
    overlap = await client.put(
        f"{api}/hours",
        json=week(
            d0={"breaks": [{"starts_at": "13:00", "ends_at": "14:00"}, {"starts_at": "13:30", "ends_at": "14:30"}]}
        ),
    )
    assert overlap.status_code == 422
    inverted = await client.put(f"{api}/hours", json=week(d0={"opens_at": "21:00", "closes_at": "09:00"}))
    assert inverted.status_code == 422

    # A closed Sunday has no online slots.
    wash = await session.scalar(select(Service.id).where(Service.slug == "detailing-wash"))
    sunday = date.today() + timedelta(days=(6 - date.today().weekday()) % 7 + 7)
    assert not any(s["available"] for s in await _slots(client, wash, sunday))


async def test_special_days_and_blocks(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    api = await _owner(client, studio, make_user)
    wash = await session.scalar(select(Service.id).where(Service.slug == "detailing-wash"))
    # A Wednesday next week: open 09-21 in the seed, independent of the current time of day.
    today = date.today()
    day = today + timedelta(days=(2 - today.weekday()) % 7 + 7)

    closed = await client.post(
        f"{api}/special-days", json={"day": day.isoformat(), "kind": "closed", "note": "Инвентаризация"}
    )
    assert closed.status_code == 201
    assert not any(s["available"] for s in await _slots(client, wash, day))
    # Saving the same date again turns it into a short day instead of a second row.
    short = await client.post(
        f"{api}/special-days", json={"day": day.isoformat(), "kind": "short", "opens_at": "11:00", "closes_at": "16:00"}
    )
    assert short.json()["id"] == closed.json()["id"]
    starts = [s["start"][11:16] for s in await _slots(client, wash, day) if s["available"]]
    assert starts and min(starts) >= "11:00" and max(starts) < "16:00"
    no_hours = await client.post(f"{api}/special-days", json={"day": day.isoformat(), "kind": "short"})
    assert no_hours.status_code == 422
    assert (await client.delete(f"{api}/special-days/{closed.json()['id']}")).status_code == 204
    assert await session.scalar(select(SpecialDay.id)) is None

    blocked = await client.post(
        f"{api}/blocks", json={"day": day.isoformat(), "starts_at": "09:00", "ends_at": "21:00", "reason": "Обучение"}
    )
    assert blocked.status_code == 201 and blocked.json()["bookings_inside"] == 0
    assert not any(s["available"] for s in await _slots(client, wash, day))
    assert (await client.delete(f"{api}/blocks/{blocked.json()['id']}")).status_code == 204
    no_box = await client.post(
        f"{api}/blocks",
        json={
            "day": day.isoformat(),
            "starts_at": "09:00",
            "ends_at": "10:00",
            "scope": "resource",
            "resource_id": 999999,
        },
    )
    assert no_box.status_code == 422


async def test_schedule_screen(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await _owner(client, studio, make_user)
    page = await client.get(f"/admin/{studio.id}/schedule", headers=HTML)
    assert page.status_code == 200, page.text
    assert (
        "Рабочие дни и часы студии" in page.text
        and "Графики мастеров" in page.text
        and "Блокировка времени" in page.text
    )
    assert 'data-repeat-prefix="days.0.breaks"' in page.text and "Андрей К." in page.text
    assert (await client.get(f"/admin/{studio.id}/schedule?month=2026-11", headers=HTML)).status_code == 200
    assert (await client.get(f"/admin/{studio.id}/schedule?month=bad", headers=HTML)).status_code == 200
