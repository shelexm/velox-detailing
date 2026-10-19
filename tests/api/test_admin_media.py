"""Media library API: upload, credits, replace in place, order, delete only when unused."""

from __future__ import annotations

import io

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaAsset, Service, Studio
from app.models.enums import Role
from tests.api.conftest import login


def jpeg(width: int = 1200, height: int = 800, color: str = "#336699") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


async def test_upload_edit_replace_delete(
    client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{studio.id}/media"

    uploaded = await client.post(
        api,
        files={"file": ("photo.jpg", jpeg(), "image/jpeg")},
        data={"alt": "Полировка капота", "author": "VÉLOX", "is_example": "false"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    assert asset["alt"] == "Полировка капота" and asset["author"] == "VÉLOX" and asset["width"] == 1200
    assert (await client.get(asset["thumb"])).status_code == 200

    patched = await client.patch(
        f"{api}/{asset['id']}", json={"alt": " Капот после полировки ", "license_url": "ftp://bad"}
    )
    assert patched.status_code == 422
    patched = await client.patch(f"{api}/{asset['id']}", json={"alt": " Капот после полировки ", "author": ""})
    assert patched.json()["alt"] == "Капот после полировки" and patched.json()["author"] is None

    # The image is used by a service: replacing keeps the id, deleting is refused.
    service = await session.scalar(select(Service).where(Service.studio_id == studio.id).limit(1))
    service.image_id = asset["id"]
    await session.commit()
    replaced = await client.post(f"{api}/{asset['id']}/file", files={"file": ("new.png", _png(), "image/png")})
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["id"] == asset["id"] and replaced.json()["width"] == 900
    assert replaced.json()["usages"] == [f"Услуга «{service.name}»"]
    assert (await client.get(asset["thumb"])).status_code == 404  # old files are gone
    refused = await client.delete(f"{api}/{asset['id']}")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "media_in_use"

    service.image_id = None
    await session.commit()
    assert (await client.delete(f"{api}/{asset['id']}")).status_code == 204
    assert await session.scalar(select(MediaAsset).where(MediaAsset.id == asset["id"])) is None


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (900, 600), "#aa8844").save(buffer, "PNG")
    return buffer.getvalue()


async def test_variants_and_fonts_have_image_and_font_types(
    client: httpx.AsyncClient, studio: Studio, make_user
) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    asset = (
        await client.post(
            f"/api/v1/admin/studios/{studio.id}/media", files={"file": ("photo.jpg", jpeg(), "image/jpeg")}
        )
    ).json()
    base = asset["thumb"].rsplit("/", 1)[0]
    for name, expected in (("w480.webp", "image/webp"), ("w480.jpg", "image/jpeg")):
        response = await client.get(f"{base}/{name}")
        assert response.status_code == 200 and response.headers["content-type"] == expected, name
    font = await client.get("/static/fonts/onest-latin.woff2")
    assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"


async def test_upload_rejects_bad_files(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{studio.id}/media"
    not_image = await client.post(api, files={"file": ("x.jpg", b"<svg onload=alert(1)>", "image/jpeg")})
    assert not_image.status_code == 422 and not_image.json()["error"]["details"][0]["field"] == "file"
    svg = await client.post(
        api, files={"file": ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml")}
    )
    assert svg.status_code == 422
    huge = await client.post(api, files={"file": ("big.jpg", b"\xff" * (5 * 1024 * 1024 + 10), "image/jpeg")})
    assert huge.status_code == 422 and "МБ" in huge.json()["error"]["details"][0]["message"]


async def test_order_and_isolation(client: httpx.AsyncClient, studio: Studio, other_studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{studio.id}/media"
    first = (await client.post(api, files={"file": ("a.jpg", jpeg(color="#111111"), "image/jpeg")})).json()
    second = (await client.post(api, files={"file": ("b.jpg", jpeg(color="#222222"), "image/jpeg")})).json()
    assert [m["id"] for m in (await client.get(api)).json()][:2] == [second["id"], first["id"]]
    assert (await client.post(f"{api}/order", json={"ids": [first["id"], second["id"]]})).status_code == 204
    assert [m["id"] for m in (await client.get(api)).json()][:2] == [first["id"], second["id"]]

    foreign = f"/api/v1/admin/studios/{other_studio.id}/media"
    assert (await client.get(foreign)).status_code == 404


async def test_masters_cannot_manage_media(client: httpx.AsyncClient, studio: Studio, make_user) -> None:
    await make_user("master@velox.test", studio, role=Role.MASTER)
    await login(client, "master@velox.test")
    assert (await client.get(f"/api/v1/admin/studios/{studio.id}/media")).status_code == 403


async def test_media_screen(client: httpx.AsyncClient, session: AsyncSession, studio: Studio, make_user) -> None:
    await make_user("owner@velox.test", studio)
    await login(client, "owner@velox.test")
    api = f"/api/v1/admin/studios/{studio.id}/media"
    asset = (await client.post(api, files={"file": ("a.jpg", jpeg(), "image/jpeg")}, data={"alt": "Капот"})).json()
    service = await session.scalar(select(Service).where(Service.studio_id == studio.id).limit(1))
    service.image_id = asset["id"]
    await session.commit()
    html = {"Accept": "text/html"}
    page = await client.get(f"/admin/{studio.id}/media", headers=html)
    assert page.status_code == 200 and "Капот" in page.text and "на сайте · 1" in page.text
    opened = await client.get(f"/admin/{studio.id}/media?open={asset['id']}", headers=html)
    assert f"Услуга «{service.name}»" in opened.text and "Заменить файл" in opened.text
    for show in ("used", "unused", "examples"):
        assert (await client.get(f"/admin/{studio.id}/media?show={show}", headers=html)).status_code == 200
