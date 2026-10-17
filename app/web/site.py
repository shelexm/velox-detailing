"""Public pages rendered on the server; the booking form talks to the public API from the browser."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.models import ServiceGroup, Studio
from app.services import booking as booking_service
from app.services.media import VARIANT_NAME
from app.web.context import load_site
from app.web.templating import build_templates, render_attrs

router = APIRouter(include_in_schema=False)
templates = build_templates()
_VARIANT = re.compile(VARIANT_NAME)
_KEY = re.compile(r"^[0-9a-f]{32}$")


async def current_studio(request: Request, session: DbSession) -> Studio:
    slug = request.app.state.settings.default_studio_slug
    studio = await session.scalar(select(Studio).where(Studio.slug == slug))
    if studio is None:
        raise NotFoundError("Студия не найдена")
    return studio


def _base_url(request: Request) -> str:
    return str(request.app.state.settings.public_base_url).rstrip("/")


def _page(request: Request, template: str, site, **extra) -> HTMLResponse:
    studio = site.studio
    script_data = render_attrs(
        {
            "studio": studio.slug,
            "bot": site.bot_username,
            "phone": site.phone_display,
            "phone-href": site.phone_href,
            "horizon": studio.horizon_days,
        }
    )
    return templates.TemplateResponse(
        request,
        template,
        {
            "site": site,
            "studio": studio,
            "media": site.media,
            "base_url": _base_url(request),
            "script_data": script_data,
            **extra,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: DbSession) -> HTMLResponse:
    studio = await current_studio(request, session)
    site = await load_site(session, studio)
    return _page(request, "site/index.html", site)


@router.get("/services/{slug}", response_class=HTMLResponse)
async def service_page(slug: str, request: Request, session: DbSession, fragment: bool = False) -> HTMLResponse:
    studio = await current_studio(request, session)
    site = await load_site(session, studio)
    view = next((g for g in site.groups if g.group.slug == slug), None)
    if view is None:
        raise NotFoundError("Услуга не найдена")
    template = "site/service_fragment.html" if fragment else "site/service.html"
    return _page(request, template, site, view=view, total=len(site.groups))


@router.get("/booking/{token}", response_class=HTMLResponse)
async def manage_booking(token: str, request: Request, session: DbSession) -> HTMLResponse:
    studio = await current_studio(request, session)
    booking = await booking_service.find_by_manage_token(session, studio.id, token)
    site = await load_site(session, studio)
    response = _page(request, "site/manage.html", site, booking=booking, token=token)
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request, session: DbSession) -> HTMLResponse:
    studio = await current_studio(request, session)
    return _page(request, "site/privacy.html", await load_site(session, studio))


@router.get("/credits", response_class=HTMLResponse)
async def credits(request: Request, session: DbSession) -> HTMLResponse:
    studio = await current_studio(request, session)
    site = await load_site(session, studio)
    used = sorted((m for m in site.media.values() if m.license), key=lambda m: (m.license or "", m.sort_order))
    return _page(request, "site/credits.html", site, assets=used)


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request) -> str:
    lines = ["User-agent: *", "Disallow: /admin", "Disallow: /api/", "Disallow: /booking/"]
    return "\n".join([*lines, f"Sitemap: {_base_url(request)}/sitemap.xml"]) + "\n"


@router.get("/sitemap.xml")
async def sitemap(request: Request, session: DbSession) -> Response:
    studio = await current_studio(request, session)
    base = _base_url(request)
    slugs = await session.scalars(
        select(ServiceGroup.slug).where(ServiceGroup.studio_id == studio.id, ServiceGroup.is_visible.is_(True))
    )
    urls = [f"{base}/", *(f"{base}/services/{slug}" for slug in slugs), f"{base}/privacy"]
    today = datetime.now(UTC).date().isoformat()
    body = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, media_type="application/xml")


@router.get("/media/{studio_id}/{key}/{filename}")
async def media_file(studio_id: int, key: str, filename: str, request: Request) -> FileResponse:
    """Only resized variants are public; originals (which may carry EXIF/GPS) never are."""
    if not _KEY.match(key) or not _VARIANT.match(filename):
        raise NotFoundError()
    root: Path = request.app.state.settings.media_root
    path = root / str(studio_id) / key / filename
    if not path.is_file():
        raise NotFoundError()
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


def render_error(request: Request, status: int, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "site/error.html", {"status": status, "message": message}, status_code=status
    )
