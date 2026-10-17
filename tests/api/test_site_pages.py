"""Public pages: render from the database, no placeholders, empty contacts hidden, media variants served."""

import io
import re

import httpx
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Booking, Service, SiteSection, Studio
from app.services.media import ingest_image

PLACEHOLDERS = re.compile(
    r"\[(ГОРОД|Город|N\]|Бренд|Имя клиента|Марка|Юрлицо|Автомобиль)|\+7 \[000\]|VELOX_BOT_USERNAME"
)


def image_bytes(color: str, size: tuple[int, int] = (1200, 800)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "JPEG")
    return buffer.getvalue()


async def test_landing_renders_without_placeholders(client: httpx.AsyncClient, site_studio: Studio) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Совершенство" in html and "Уход, который видно под любым светом" in html
    assert re.search(r"от[\s ]25[\s ]000[\s ]₽", html)  # prices from the design
    assert not PLACEHOLDERS.search(html), PLACEHOLDERS.search(html)
    assert "—" not in html
    # No contacts were configured: no phone links, no Telegram buttons, no empty rows.
    assert "tel:" not in html and "t.me/" not in html
    assert ">АДРЕС<" not in html and ">ТЕЛЕФОН<" not in html
    # Hours come from the studio schedule.
    assert "Пн–Сб" in html and "09:00–21:00" in html
    assert "data-booking-form" in html


async def test_partial_contacts_are_shown_individually(
    client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio
) -> None:
    await session.execute(
        update(Studio)
        .where(Studio.id == site_studio.id)
        .values(phone="+79130000001", telegram_bot_username="velox_test_bot", city="Тестоград")
    )
    await session.commit()
    html = (await client.get("/")).text
    assert "tel:+79130000001" in html and "+7 913 000-00-01" in html
    assert "https://t.me/velox_test_bot" in html and "<svg" in html  # QR code for the bot
    assert "СТУДИЯ ДЕТЕЙЛИНГА · ТЕСТОГРАД" in html
    assert "Тестоград" in html  # the city alone fills the address row
    assert "ИНН" not in html and "WhatsApp" not in html


async def test_section_edits_and_visibility_reach_the_page(
    client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio
) -> None:
    hero = await session.get(SiteSection, (site_studio.id, "hero"))
    hero.content = {**hero.content, "title_lines": ["Новый заголовок"]}
    prices = await session.get(SiteSection, (site_studio.id, "prices"))
    prices.is_visible = False
    await session.commit()
    html = (await client.get("/")).text
    assert "Новый заголовок" in html and "Совершенство" not in html
    assert 'id="prices"' not in html


async def test_service_page_and_fragment(client: httpx.AsyncClient, site_studio: Studio) -> None:
    page = await client.get("/services/polishing")
    assert page.status_code == 200
    assert "Лёгкая полировка" in page.text and "Восстановительная полировка" in page.text
    assert "ЧТО ВХОДИТ" in page.text
    fragment = await client.get("/services/polishing?fragment=1")
    assert fragment.status_code == 200 and "<html" not in fragment.text
    missing = await client.get("/services/nope", headers={"Accept": "text/html"})
    assert missing.status_code == 404 and "Страница не найдена" in missing.text


async def test_service_photo_is_rendered_and_served(
    client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio, settings: Settings
) -> None:
    asset = await ingest_image(
        session,
        studio_id=site_studio.id,
        media_root=settings.media_root,
        data=image_bytes("#334455"),
        original_name="card.jpg",
        alt="Тестовое фото карточки",
    )
    await session.execute(update(Service).where(Service.studio_id == site_studio.id).values(image_id=None))
    from app.models import ServiceGroup

    await session.execute(
        update(ServiceGroup)
        .where(ServiceGroup.studio_id == site_studio.id, ServiceGroup.slug == "ceramic")
        .values(image_id=asset.id)
    )
    await session.commit()
    html = (await client.get("/")).text
    assert 'alt="Тестовое фото карточки"' in html
    url = re.search(r'src="(/media/[^"]+\.jpg)"', html).group(1)
    image = await client.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    assert "immutable" in image.headers["cache-control"]
    original = url.rsplit("/", 1)[0] + "/original.jpg"
    assert (await client.get(original)).status_code == 404  # originals are never served


async def test_static_files_and_text_pages(client: httpx.AsyncClient, site_studio: Studio) -> None:
    for path in ("/static/css/site.css", "/static/fonts/onest-cyrillic.woff2", "/static/img/favicon.svg"):
        assert (await client.get(path)).status_code == 200, path
    assert "Disallow: /admin" in (await client.get("/robots.txt")).text
    assert "<urlset" in (await client.get("/sitemap.xml")).text
    assert "персональных данных" in (await client.get("/privacy")).text
    assert (await client.get("/credits")).status_code == 200


async def test_every_static_reference_exists_with_exact_case(client: httpx.AsyncClient, site_studio: Studio) -> None:
    from app.web.templating import STATIC_DIR

    html = (await client.get("/")).text
    css = (STATIC_DIR / "css" / "site.css").read_text(encoding="utf-8")
    paths = set(re.findall(r'/static/([\w./-]+?)(?:\?v=\w+)?["\')]', html + css))
    assert paths
    for rel in paths:
        parent = STATIC_DIR / rel
        assert parent.name in {p.name for p in parent.parent.iterdir()}, rel


async def test_manage_page(client: httpx.AsyncClient, session: AsyncSession, site_studio: Studio) -> None:
    from tests.api.conftest import first_free_slot

    service = await session.scalar(select(Service.id).where(Service.slug == "ceramic-coating"))
    start = await first_free_slot(client, "velox", service)
    created = await client.post(
        "/api/v1/public/studios/velox/bookings",
        json={"service_id": service, "starts_at": start, "name": "Алексей", "phone": "+79134521807", "consent": True},
    )
    token = created.json()["manage_url"].rsplit("/", 1)[-1]
    page = await client.get(f"/booking/{token}")
    assert page.status_code == 200 and "Керамическое покрытие" in page.text
    assert page.headers["x-robots-tag"] == "noindex"
    assert await session.scalar(select(Booking.id)) is not None
    # No bot and no phone yet: the reschedule hint must not point at channels that do not exist.
    assert "Telegram-бота" not in page.text and "отмените запись и выберите новое" in page.text

    site_studio.phone = "+79001234567"
    site_studio.telegram_bot_username = "velox_test_bot"
    await session.commit()
    page = await client.get(f"/booking/{token}")
    hint = page.text[page.text.index("Отменить онлайн") :][:600]
    assert 'через <a href="https://t.me/velox_test_bot"' in hint, hint
    assert 'по телефону <a class="mono" href="tel:+79001234567">' in page.text


async def test_static_cache_headers(client: httpx.AsyncClient) -> None:
    module = await client.get("/static/js/panel.js")
    assert module.status_code == 200 and module.headers["cache-control"] == "no-cache"
    versioned = await client.get("/static/js/panel.js?v=abc")
    assert "immutable" in versioned.headers["cache-control"]
    style = await client.get("/static/css/panel.css")
    assert style.headers["cache-control"] == "public, max-age=3600"
