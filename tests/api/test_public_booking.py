import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service, Studio
from tests.api.conftest import first_free_slot, login

BASE = "/api/v1/public/studios/velox"


def form(service_id: int, start: str, **extra) -> dict:
    return {
        "service_id": service_id,
        "starts_at": start,
        "name": "Алексей",
        "phone": "+7 913 452-18-07",
        "vehicle": "Audi A6, 2021",
        "consent": True,
        **extra,
    }


async def service_by_slug(session: AsyncSession, slug: str) -> int:
    return await session.scalar(select(Service.id).where(Service.slug == slug, Service.studio_id == 1))


async def test_studio_info_hides_empty_contacts(client: httpx.AsyncClient, studio: Studio) -> None:
    body = (await client.get(BASE)).json()
    assert body["name"] == "VÉLOX Detailing Studio"
    assert "phone" not in body and "address" not in body and "inn" not in body


async def test_services_for_the_form(client: httpx.AsyncClient, studio: Studio) -> None:
    services = {s["slug"]: s for s in (await client.get(f"{BASE}/services")).json()}
    assert "ppf-full" not in services  # "Только после осмотра" is not bookable online
    assert services["ceramic-coating"]["price_from"] == 45000
    assert [m["short_name"] for m in services["light-polish"]["staff"]] == ["Андрей К.", "Максим Р."]
    assert services["interior-cleaning"]["staff"] == []  # the studio assigns the master
    assert services["light-polish"]["group_slug"] == "polishing"
    assert services["light-polish"]["group_short_title"] == "Полировка"


async def test_book_then_slot_is_taken(client: httpx.AsyncClient, session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_by_slug(session, "ceramic-coating")
    start = await first_free_slot(client, "velox", ceramic)

    created = await client.post(f"{BASE}/bookings", json=form(ceramic, start))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["number"] == 1001 and body["status"] == "new" and body["staff_name"] == "Андрей К."
    assert body["manage_url"].startswith("http://127.0.0.1:8000/booking/")

    taken = await client.post(f"{BASE}/bookings", json=form(ceramic, start, phone="+79130000001"))
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "slot_taken"
    assert taken.json()["error"]["details"]["alternatives"]

    day = (
        await client.get(f"{BASE}/availability", params={"service_id": ceramic, "date_from": start[:10], "days": 1})
    ).json()
    slot = next(s for s in day["days"][0]["slots"] if s["start"] == start)
    assert slot["available"] is False


async def test_validation_errors_name_fields_without_echoing_input(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio
) -> None:
    ceramic = await service_by_slug(session, "ceramic-coating")
    start = await first_free_slot(client, "velox", ceramic)
    response = await client.post(f"{BASE}/bookings", json=form(ceramic, start, phone="+7 913 45", consent=False))
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert fields == {"phone", "consent"}
    assert "913 45" not in response.text

    schema_error = await client.post(f"{BASE}/bookings", json={"service_id": "x", "name": "Секретное Имя"})
    assert schema_error.status_code == 422
    assert "Секретное" not in schema_error.text


async def test_honeypot_and_unknown_studio(client: httpx.AsyncClient, session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_by_slug(session, "ceramic-coating")
    start = await first_free_slot(client, "velox", ceramic)
    assert (await client.post(f"{BASE}/bookings", json=form(ceramic, start, website="http://spam"))).status_code == 422
    assert (await client.get("/api/v1/public/studios/nope/services")).status_code == 404


async def test_booking_requests_are_rate_limited(client: httpx.AsyncClient, studio: Studio) -> None:
    statuses = [(await client.post(f"{BASE}/bookings", json={"bad": True})).status_code for _ in range(11)]
    assert statuses[:10] == [422] * 10 and statuses[10] == 429


async def test_manage_link_view_calendar_and_cancel(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio
) -> None:
    ceramic = await service_by_slug(session, "ceramic-coating")
    # Book far enough ahead to be inside the online cancellation window.
    response = await client.get(f"{BASE}/availability", params={"service_id": ceramic, "days": 14})
    slots = [s["start"] for d in response.json()["days"] for s in d["slots"] if s["available"]]
    created = (await client.post(f"{BASE}/bookings", json=form(ceramic, slots[-1]))).json()
    token = created["manage_url"].rsplit("/", 1)[-1]

    view = await client.get(f"{BASE}/bookings/manage/{token}")
    assert view.status_code == 200 and view.json()["can_cancel"] is True
    assert "phone" not in view.json()

    ics = await client.get(f"{BASE}/bookings/manage/{token}/calendar.ics")
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in ics.text and "Керамическое покрытие" in ics.text

    cancelled = await client.post(f"{BASE}/bookings/manage/{token}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (await client.get(f"{BASE}/bookings/manage/not-a-token")).status_code == 404


async def test_site_booking_appears_in_the_panel(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    ceramic = await service_by_slug(session, "ceramic-coating")
    start = await first_free_slot(client, "velox", ceramic)
    await client.post(f"{BASE}/bookings", json=form(ceramic, start))
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    rows = (
        await client.get(
            f"/api/v1/admin/studios/{studio.id}/bookings",
            params={"date_from": start[:10] + "T00:00:00", "date_to": start[:10] + "T23:59:59"},
        )
    ).json()
    assert [(r["number"], r["source"], r["phone"]) for r in rows] == [(1001, "site", "+7 913 452-18-07")]


async def test_security_headers(client: httpx.AsyncClient, studio: Studio) -> None:
    response = await client.get(BASE)
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_odd_input_is_a_clean_error_not_a_500(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio
) -> None:
    ceramic = await service_by_slug(session, "ceramic-coating")
    # Dates far outside any calendar used to overflow datetime arithmetic.
    for day in ("9999-12-31", "0001-01-01"):
        response = await client.get(f"{BASE}/availability", params={"service_id": ceramic, "date_from": day})
        assert response.status_code == 422, day
    # Full-width digits pass \D but not the database CHECK; they must be refused as a bad phone.
    start = await first_free_slot(client, "velox", ceramic)
    response = await client.post(f"{BASE}/bookings", json=form(ceramic, start, phone="+7 9１３ 452-18-07"))
    assert response.status_code == 422
    assert "phone" in {d["field"] for d in response.json()["error"]["details"]}


async def test_same_request_twice_and_phone_flooding(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio
) -> None:
    from app.services.booking import MAX_ACTIVE_ONLINE_REQUESTS

    inspection = await service_by_slug(session, "inspection")  # three masters and two boxes: a twin would fit
    start = await first_free_slot(client, "velox", inspection)
    first = await client.post(f"{BASE}/bookings", json=form(inspection, start))
    assert first.status_code == 201
    # A retry after a lost answer (or a second tab) must not occupy another box and master.
    again = await client.post(f"{BASE}/bookings", json=form(inspection, start))
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_booking"

    # One phone cannot fill the calendar: the limit counts its active bookings.
    days = (await client.get(f"{BASE}/availability", params={"service_id": inspection, "days": 14})).json()["days"]
    other_slots = [
        slot["start"] for day in days for slot in day["slots"] if slot["available"] and slot["start"] != start
    ]
    created = 1
    for slot in other_slots[: MAX_ACTIVE_ONLINE_REQUESTS + 2]:
        response = await client.post(f"{BASE}/bookings", json=form(inspection, slot))
        if response.status_code == 201:
            created += 1
        else:
            assert response.status_code == 409 and response.json()["error"]["code"] == "too_many_active_bookings"
            break
    assert created == MAX_ACTIVE_ONLINE_REQUESTS
