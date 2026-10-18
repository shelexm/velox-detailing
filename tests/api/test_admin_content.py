"""Site content API. Acceptance rule of the panel: a change of every landing block shows up on the site."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.sections import SECTION_MODELS
from app.models import Studio
from tests.api.conftest import login

HTML = {"Accept": "text/html"}
# Which text of each block to change; the marker must then appear on the landing page.
EDITED_FIELD = {
    "hero": "lead",
    "services": "title",
    "works": "title",
    "prices": "title",
    "telegram": "title",
    "about": "title",
    "materials": "title",
    "process": "title",
    "reviews": "title",
    "gift": "title",
    "contacts": "title",
    "final_cta": "title",
    "footer": "about",
    "seo": "title",
}


def jpeg(color: str = "#336699") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 800), color).save(buffer, "JPEG")
    return buffer.getvalue()


async def _owner(client: httpx.AsyncClient, studio: Studio, make_user) -> str:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    return f"/api/v1/admin/studios/{studio.id}"


def test_every_block_is_covered() -> None:
    assert set(EDITED_FIELD) == set(SECTION_MODELS)


@pytest.mark.parametrize("key", list(EDITED_FIELD))
async def test_block_change_reaches_the_site(
    key: str, client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio, make_user
) -> None:
    api = await _owner(client, site_studio, make_user)
    if key == "telegram":  # the block is shown only when the bot is configured
        site_studio.telegram_bot_username = "velox_test_bot"
        await session.commit()
    if key == "works":  # the block is shown only when a before/after pair has both photos
        ids = [
            (await client.post(f"{api}/media", files={"file": (f"{c}.jpg", jpeg(c), "image/jpeg")})).json()["id"]
            for c in ("#111111", "#eeeeee")
        ]
        await client.post(
            f"{api}/portfolio", json={"title": "Пара", "before_image_id": ids[0], "after_image_id": ids[1]}
        )
    marker = f"Проверка {key} 7Q"
    saved = await client.patch(f"{api}/sections/{key}", json={"content": {EDITED_FIELD[key]: marker}})
    assert saved.status_code == 200, saved.text
    landing = await client.get("/", headers=HTML)
    assert marker in landing.text, f"{key}: new text is not on the page"


async def test_block_validation_and_visibility(client: httpx.AsyncClient, site_studio: Studio, make_user) -> None:
    api = await _owner(client, site_studio, make_user)
    empty = await client.patch(f"{api}/sections/hero", json={"content": {"title_lines": []}})
    assert empty.status_code == 422 and empty.json()["error"]["details"][0]["field"] == "title_lines"
    unknown = await client.patch(f"{api}/sections/hero", json={"content": {"nope": "x"}})
    assert unknown.status_code == 422
    nested = await client.patch(
        f"{api}/sections/about", json={"content": {"items": [{"icon": "bad", "title": "x", "text": "y"}]}}
    )
    assert nested.status_code == 422 and nested.json()["error"]["details"][0]["field"] == "items.0.icon"
    foreign = await client.patch(f"{api}/sections/final_cta", json={"content": {"image_id": 999999}})
    assert foreign.status_code == 422
    assert (await client.patch(f"{api}/sections/nope", json={"is_visible": False})).status_code == 404
    assert (await client.patch(f"{api}/sections/hero", json={"is_visible": False})).status_code == 422

    hidden = await client.patch(f"{api}/sections/process", json={"is_visible": False})
    assert hidden.json()["is_visible"] is False
    assert "Пять шагов от записи до выдачи" not in (await client.get("/", headers=HTML)).text

    await client.patch(f"{api}/sections/about", json={"content": {"title": "Новый заголовок"}})
    reset = await client.post(f"{api}/sections/about/reset")
    assert reset.json()["content"]["title"] == "Почему нам доверяют ключи"

    order = [
        "final_cta",
        "gift",
        "services",
        "works",
        "prices",
        "telegram",
        "about",
        "materials",
        "process",
        "reviews",
        "contacts",
    ]
    assert (await client.post(f"{api}/sections/order", json={"keys": order})).status_code == 204
    page = (await client.get("/", headers=HTML)).text
    assert page.index('id="final"') < page.index('id="services"')


async def test_cases_reviews_gifts(client: httpx.AsyncClient, site_studio: Studio, make_user) -> None:
    api = await _owner(client, site_studio, make_user)
    before = (await client.post(f"{api}/media", files={"file": ("b.jpg", jpeg("#222222"), "image/jpeg")})).json()
    after = (await client.post(f"{api}/media", files={"file": ("a.jpg", jpeg("#dddddd"), "image/jpeg")})).json()

    case = await client.post(
        f"{api}/portfolio",
        json={
            "title": "Полировка BMW",
            "before_image_id": before["id"],
            "after_image_id": after["id"],
            "is_example": False,
        },
    )
    assert case.status_code == 201, case.text
    assert case.json()["before_label"] == "ДО"
    assert "Полировка BMW" in (await client.get("/", headers=HTML)).text
    assert (await client.patch(f"{api}/portfolio/{case.json()['id']}", json={"is_published": False})).status_code == 200
    assert "Полировка BMW" not in (await client.get("/", headers=HTML)).text
    assert (await client.post(f"{api}/portfolio", json={"title": "x", "after_image_id": 999999})).status_code == 422
    assert (await client.delete(f"{api}/portfolio/{case.json()['id']}")).status_code == 204

    review = await client.post(
        f"{api}/reviews",
        json={"text": "Отличная  работа,\n  спасибо!", "rating": 5, "author_name": "Ирина", "is_demo": False},
    )
    assert review.status_code == 201 and review.json()["text"] == "Отличная работа,\nспасибо!"
    assert "Ирина" in (await client.get("/", headers=HTML)).text
    assert (await client.patch(f"{api}/reviews/{review.json()['id']}", json={"rating": 6})).status_code == 422
    assert (
        await client.post(f"{api}/reviews", json={"text": "x", "source_url": "javascript:alert(1)"})
    ).status_code == 422

    gift = await client.post(
        f"{api}/gifts", json={"label": "7 000 ₽", "value_text": "7 000 ₽", "subtitle": "На любую услугу"}
    )
    assert gift.status_code == 201
    assert "7 000 ₽" in (await client.get("/", headers=HTML)).text
    assert (await client.patch(f"{api}/gifts/{gift.json()['id']}", json={"is_visible": False})).json()[
        "is_visible"
    ] is False
    assert (await client.delete(f"{api}/gifts/{gift.json()['id']}")).status_code == 204


async def test_content_screens(client: httpx.AsyncClient, site_studio: Studio, make_user) -> None:
    api = await _owner(client, site_studio, make_user)
    base = f"/admin/{site_studio.id}"
    for key in EDITED_FIELD:
        page = await client.get(f"{base}/content?block={key}", headers=HTML)
        assert page.status_code == 200, (key, page.text[:300])
        assert 'name="content.' in page.text, key
    about = await client.get(f"{base}/content?block=about", headers=HTML)
    assert 'data-repeat-prefix="content.items"' in about.text and 'name="content.items.0.icon"' in about.text
    assert "Почему нам доверяют ключи" in about.text
    assert (await client.get(f"{base}/content?tab=gifts", headers=HTML)).status_code == 200

    review = (await client.post(f"{api}/reviews", json={"text": "Всё отлично", "is_demo": True})).json()
    reviews = await client.get(f"{base}/reviews?open={review['id']}", headers=HTML)
    assert reviews.status_code == 200 and "Всё отлично" in reviews.text and "ДЕМО" in reviews.text
    assert (await client.get(f"{base}/reviews?new=1", headers=HTML)).status_code == 200
    case = (await client.post(f"{api}/portfolio", json={"title": "Пара без фото"})).json()
    portfolio = await client.get(f"{base}/portfolio?open={case['id']}", headers=HTML)
    assert portfolio.status_code == 200 and "нужны оба фото" in portfolio.text
    assert (await client.get(f"{base}/portfolio?new=1", headers=HTML)).status_code == 200
