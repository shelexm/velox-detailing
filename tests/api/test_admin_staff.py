"""Masters API: profile, hours inside the studio hours, services, absences, retire."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Service, ServiceStaff, Staff, StaffHours, Studio
from app.models.enums import BookingStatus
from tests.api.conftest import first_free_slot, login

HTML = {"Accept": "text/html"}


def week(**overrides) -> dict:
    days = [{"weekday": i, "is_working": i < 5, "starts_at": "10:00", "ends_at": "18:00"} for i in range(7)]
    for weekday, value in overrides.items():
        days[int(weekday[1:])] |= value
    return {"days": days}


async def _owner(client: httpx.AsyncClient, studio: Studio, make_user) -> str:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    return f"/api/v1/admin/studios/{studio.id}/staff"


async def test_create_edit_and_hours(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    api = await _owner(client, studio, make_user)
    created = await client.post(
        api, json={"full_name": " Ирина  Смирнова ", "phone": "8 900 111-22-33", "specializations": ["Химчистка", " "]}
    )
    assert created.status_code == 201, created.text
    master = created.json()
    assert master["full_name"] == "Ирина Смирнова" and master["short_name"] == "Ирина С."
    assert master["phone"] == "+79001112233" and master["specializations"] == ["Химчистка"]
    # A new master starts with the studio hours.
    hours = list(await session.scalars(select(StaffHours).where(StaffHours.staff_id == master["id"])))
    assert len(hours) == 7

    patched = await client.patch(f"{api}/{master['id']}", json={"title": "Мастер", "since_year": 2021})
    assert patched.json()["since_year"] == 2021
    assert (await client.patch(f"{api}/{master['id']}", json={"since_year": 1900})).status_code == 422
    assert (await client.patch(f"{api}/{master['id']}", json={"phone": "123"})).status_code == 422

    ok = await client.put(f"{api}/{master['id']}/hours", json=week())
    assert ok.status_code == 204
    # Studio opens at 09:00 on weekdays: a shift from 07:00 is refused for that day only.
    early = await client.put(f"{api}/{master['id']}/hours", json=week(d0={"starts_at": "07:00"}))
    assert early.status_code == 422 and early.json()["error"]["details"][0]["field"] == "days.0"
    broken = await client.put(f"{api}/{master['id']}/hours", json=week(d1={"starts_at": "18:00", "ends_at": "10:00"}))
    assert broken.status_code == 422
    missing = await client.put(f"{api}/{master['id']}/hours", json={"days": week()["days"][:6]})
    assert missing.status_code == 422


async def test_services_absences_and_retire(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    api = await _owner(client, studio, make_user)
    andrey = await session.scalar(select(Staff).where(Staff.studio_id == studio.id, Staff.short_name == "Андрей К."))
    polish = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))

    assert (await client.put(f"{api}/{andrey.id}/services", json={"ids": [polish]})).status_code == 204
    linked = set(await session.scalars(select(ServiceStaff.service_id).where(ServiceStaff.staff_id == andrey.id)))
    assert linked == {polish}
    assert (await client.put(f"{api}/{andrey.id}/services", json={"ids": [999999]})).status_code == 422

    # A booking with Andrey, then an absence over that day reports the clash.
    start = await first_free_slot(client, "velox", polish, staff_id=andrey.id)
    booked = await client.post(
        "/api/v1/public/studios/velox/bookings",
        json={
            "service_id": polish,
            "staff_id": andrey.id,
            "starts_at": start,
            "name": "Тест",
            "phone": "+79001234567",
            "consent": True,
        },
    )
    assert booked.status_code == 201, booked.text
    day = date.fromisoformat(start[:10])
    absence = await client.post(
        f"{api}/{andrey.id}/absences",
        json={"starts_on": day.isoformat(), "ends_on": (day + timedelta(days=2)).isoformat()},
    )
    assert absence.status_code == 201 and absence.json()["bookings_inside"] == 1
    backwards = await client.post(
        f"{api}/{andrey.id}/absences",
        json={"starts_on": day.isoformat(), "ends_on": (day - timedelta(days=1)).isoformat()},
    )
    assert backwards.status_code == 422

    # Off days are no longer offered online.
    slots = await client.get(
        "/api/v1/public/studios/velox/availability",
        params={"service_id": polish, "staff_id": andrey.id, "date_from": day.isoformat(), "days": 1},
    )
    assert not any(s["available"] for s in slots.json()["days"][0]["slots"])
    assert (await client.delete(f"{api}/{andrey.id}/absences/{absence.json()['id']}")).status_code == 204

    refused = await client.delete(f"{api}/{andrey.id}")
    assert refused.status_code == 409 and refused.json()["error"]["details"]["bookings"] == 1
    booking = await session.scalar(select(Booking).where(Booking.staff_id == andrey.id))
    booking.status = BookingStatus.CANCELLED
    await session.commit()
    assert (await client.delete(f"{api}/{andrey.id}")).status_code == 204
    await session.refresh(andrey)
    assert andrey.is_active is False


async def test_staff_screen(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    await _owner(client, studio, make_user)
    page = await client.get(f"/admin/{studio.id}/staff", headers=HTML)
    assert page.status_code == 200, page.text
    assert "Андрей Ковалёв" in page.text and "Индивидуальный график" in page.text and "Занятость на неделе" in page.text
    elena = await session.scalar(select(Staff.id).where(Staff.short_name == "Елена О."))
    opened = await client.get(f"/admin/{studio.id}/staff?open={elena}", headers=HTML)
    assert "Елена Орлова" in opened.text and "онлайн-запись через студию" in opened.text
    assert 'name="days.6.is_working"' in opened.text
    assert "Новый мастер" in (await client.get(f"/admin/{studio.id}/staff?new=1", headers=HTML)).text
    assert '<dialog class="confirm" data-confirm-dialog ' in page.text
