"""Catalog API: services, price list sections and landing directions; changes reach the site."""

from __future__ import annotations

import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import slugify
from app.models import ServiceCategory, ServiceGroup, Staff, Studio
from tests.api.conftest import login


def test_slugify() -> None:
    assert slugify("Керамика дисков") == "keramika-diskov"
    assert slugify("Плёнка: зоны риска!") == "plenka-zony-riska"
    assert slugify("???", fallback="service") == "service"


async def _owner(client: httpx.AsyncClient, studio: Studio, make_user) -> str:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    return f"/api/v1/admin/studios/{studio.id}"


async def test_service_lifecycle(
    client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio, make_user
) -> None:
    studio = site_studio
    api = await _owner(client, studio, make_user)
    category = await session.scalar(select(ServiceCategory.id).where(ServiceCategory.studio_id == studio.id).limit(1))
    staff = list(await session.scalars(select(Staff.id).where(Staff.studio_id == studio.id).limit(2)))

    created = await client.post(
        f"{api}/services",
        json={
            "name": "Антидождь  на стёкла",
            "category_id": category,
            "short_description": "Капли скатываются на скорости от 60 км/ч",
            "price_from": 3500,
            "duration_value": 1,
            "duration_unit": "hours",
            "duration_label": "1 ч",
            "staff_ids": staff,
            "client_selects_staff": True,
        },
    )
    assert created.status_code == 201, created.text
    service = created.json()
    assert service["name"] == "Антидождь на стёкла" and service["slug"] == "antidozhd-na-stekla"
    assert service["duration_minutes"] == 60 and service["duration_days"] is None
    assert sorted(service["staff_ids"]) == sorted(staff)

    # It is bookable and listed for the public form right away.
    public = (await client.get("/api/v1/public/studios/velox/services")).json()
    assert any(s["slug"] == "antidozhd-na-stekla" and s["price_from"] == 3500 for s in public)

    days = await client.patch(
        f"{api}/services/{service['id']}", json={"duration_value": 2, "duration_unit": "days", "price_from": 4000}
    )
    assert days.json()["duration_days"] == 2 and days.json()["duration_minutes"] is None
    no_master = await client.patch(f"{api}/services/{service['id']}", json={"staff_ids": []})
    assert no_master.status_code == 422 and no_master.json()["error"]["details"][0]["field"] == "staff_ids"
    studio_assigns = await client.patch(
        f"{api}/services/{service['id']}", json={"staff_ids": [], "client_selects_staff": False}
    )
    assert studio_assigns.status_code == 200 and studio_assigns.json()["client_selects_staff"] is False
    too_long = await client.patch(f"{api}/services/{service['id']}", json={"short_description": "x" * 161})
    assert too_long.status_code == 422
    half = await client.patch(f"{api}/services/{service['id']}", json={"duration_value": 3})
    assert half.status_code == 422

    page = await client.get("/", headers={"Accept": "text/html"})
    assert "Антидождь на стёкла" in page.text and re.search(r"4[\s ]000", page.text)

    assert (await client.delete(f"{api}/services/{service['id']}")).status_code == 204
    public = (await client.get("/api/v1/public/studios/velox/services")).json()
    assert all(s["slug"] != "antidozhd-na-stekla" for s in public)
    assert (await client.get(f"{api}/services/{service['id']}")).status_code == 404


async def test_ids_from_another_studio_are_rejected(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, other_studio: Studio, make_user
) -> None:
    api = await _owner(client, studio, make_user)
    foreign_staff = await session.scalar(select(Staff.id).where(Staff.studio_id == other_studio.id).limit(1))
    foreign_category = await session.scalar(
        select(ServiceCategory.id).where(ServiceCategory.studio_id == other_studio.id).limit(1)
    )
    base = {"name": "Тест", "duration_value": 30, "duration_unit": "minutes"}
    staff = await client.post(f"{api}/services", json={**base, "staff_ids": [foreign_staff]})
    assert staff.status_code == 422 and staff.json()["error"]["details"][0]["field"] == "staff_ids"
    category = await client.post(f"{api}/services", json={**base, "category_id": foreign_category})
    assert category.status_code == 422 and category.json()["error"]["details"][0]["field"] == "category_id"
    image = await client.post(f"{api}/services", json={**base, "image_id": 999999})
    assert image.status_code == 422


async def test_categories_and_groups(
    client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio, make_user
) -> None:
    studio = site_studio
    api = await _owner(client, studio, make_user)
    created = await client.post(f"{api}/categories", json={"name": "Мотоциклы"})
    assert created.status_code == 201 and created.json()["slug"] == "mototsikly"
    renamed = await client.patch(f"{api}/categories/{created.json()['id']}", json={"name": "Мото"})
    assert renamed.json()["name"] == "Мото"
    used = await session.scalar(select(ServiceCategory.id).where(ServiceCategory.slug == "body"))
    assert (await client.delete(f"{api}/categories/{used}")).status_code == 409
    assert (await client.delete(f"{api}/categories/{created.json()['id']}")).status_code == 204

    group = await session.scalar(select(ServiceGroup).where(ServiceGroup.slug == "polishing"))
    patched = await client.patch(
        f"{api}/groups/{group.id}",
        json={
            "title": "Полировка кузова и фар",
            "features": ["Замер ЛКП", " ", "Свет 6500 K"],
            "detail": {"description": "Новый текст страницы", "includes": ["Мойка", ""], "term": "1 день"},
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["features"] == ["Замер ЛКП", "Свет 6500 K"]
    assert patched.json()["detail"]["includes"] == ["Мойка"]
    page = await client.get("/services/polishing", headers={"Accept": "text/html"})
    assert "Полировка кузова и фар" in page.text and "Новый текст страницы" in page.text
    assert (await client.delete(f"{api}/groups/{group.id}")).status_code == 409  # services are attached

    # Too many lines in "Что входит" is a message at the field, not a server error.
    too_many = await client.patch(
        f"{api}/groups/{group.id}", json={"detail": {"includes": [f"п{n}" for n in range(13)]}}
    )
    assert too_many.status_code == 422, too_many.text
    detail = too_many.json()["error"]["details"][0]
    assert detail["field"] == "detail.includes" and detail["message"] == "Слишком много: максимум 12"

    hidden = await client.patch(f"{api}/groups/{group.id}", json={"is_visible": False})
    assert hidden.json()["is_visible"] is False
    landing = await client.get("/", headers={"Accept": "text/html"})
    assert "Полировка кузова и фар" not in landing.text
