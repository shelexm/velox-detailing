"""Studio brand: the logo word, its tagline and an optional logo image, set in the panel settings."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Studio
from tests.api.conftest import login
from tests.api.test_admin_media import jpeg

HTML = {"Accept": "text/html"}
VELOX_WORD = '<span>V</span><span class="logo-e">E<span class="logo-accent" aria-hidden="true"></span></span>'


async def test_brand_word_tagline_and_image(
    client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio, other_studio: Studio, make_user
) -> None:
    # The seeded studio keeps the VÉLOX word with the accent stroke of the design.
    home = (await client.get("/", headers=HTML)).text
    assert VELOX_WORD in home and '<span class="logo-sub">DETAILING STUDIO</span>' in home
    assert ">V<" in (await client.get("/favicon.svg")).text

    await make_user("owner@velox.test", site_studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{site_studio.id}"
    saved = await client.patch(f"{api}/settings", json={"brand_name": "  Авто   Блеск ", "brand_tagline": "ДЕТЕЙЛИНГ"})
    assert saved.status_code == 200 and saved.json()["brand_name"] == "Авто Блеск"

    home = (await client.get("/", headers=HTML)).text
    assert VELOX_WORD not in home
    assert "<span>А</span><span>в</span><span>т</span><span>о</span>" in home
    assert '<span class="logo-sub">ДЕТЕЙЛИНГ</span>' in home
    assert ">А<" in (await client.get("/favicon.svg")).text
    panel = (await client.get(f"/admin/{site_studio.id}/settings", headers=HTML)).text
    assert 'aria-label="Авто Блеск"' in panel and "Логотип-картинка" in panel
    assert "Авто Блеск · запись" in (await client.get("/tg/app", headers=HTML)).text

    # An empty brand word falls back to the studio name.
    await client.patch(f"{api}/settings", json={"brand_name": ""})
    assert "<span>D</span><span>e</span><span>t</span>" in (await client.get("/", headers=HTML)).text

    # A logo image from the library replaces the word everywhere and cannot be deleted while it is the logo.
    uploaded = await client.post(f"{api}/media", files={"file": ("logo.jpg", jpeg(800, 240), "image/jpeg")})
    assert uploaded.status_code == 201, uploaded.text
    logo_id = uploaded.json()["id"]
    assert (await client.patch(f"{api}/settings", json={"logo_image_id": logo_id})).status_code == 200
    home = (await client.get("/", headers=HTML)).text
    assert 'class="logo-img"' in home and "<span>D</span><span>e</span>" not in home
    assert 'class="pn-logo__img"' in (await client.get(f"/admin/{site_studio.id}/settings", headers=HTML)).text
    refused = await client.delete(f"{api}/media/{logo_id}")
    assert refused.status_code == 409 and "Логотип студии" in refused.text

    # Someone else's photo cannot become the logo.
    foreign = await client.patch(f"{api}/settings", json={"logo_image_id": 999999})
    assert foreign.status_code == 422 and foreign.json()["error"]["details"][0]["field"] == "logo_image_id"

    # Removing the image brings the word back.
    assert (await client.patch(f"{api}/settings", json={"logo_image_id": None})).status_code == 200
    assert 'class="logo-img"' not in (await client.get("/", headers=HTML)).text
    login_page = (
        await httpx.AsyncClient(transport=client._transport, base_url="http://testserver").get(
            "/admin/login", headers=HTML
        )
    ).text
    assert "pn-logo__word" in login_page
