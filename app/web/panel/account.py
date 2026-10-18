"""Sign-in page, studio picker and the account page (password change)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response

from app.api.deps import DbSession
from app.core import security
from app.services.auth import resolve_session
from app.web.panel.common import AnyPanel, default_brand, panel_user, render

router = APIRouter()


def _safe_next(value: str | None) -> str:
    # Only local panel paths: never redirect to another site after signing in.
    if value and value.startswith("/admin") and not value.startswith("//") and "\\" not in value:
        return value
    return "/admin"


@router.get("/admin/login")
async def login_page(
    request: Request, session: DbSession, next: Annotated[str | None, Query(max_length=300)] = None
) -> Response:
    if await resolve_session(session, request.cookies.get(security.SESSION_COOKIE)):
        return RedirectResponse(_safe_next(next), status_code=303)
    brand = await default_brand(request, session)
    return render(request, "panel/login.html", None, next_url=_safe_next(next), brand=brand)


@router.get("/admin")
async def panel_home(request: Request, session: DbSession, user: Annotated[tuple, Depends(panel_user)]) -> Response:
    _user, rows = user
    if len(rows) == 1:
        return RedirectResponse(f"/admin/{rows[0][1].id}/", status_code=303)
    brand = await default_brand(request, session)
    return render(request, "panel/studios.html", None, rows=rows, user=_user, brand=brand)


@router.get("/admin/{studio_id}/more")
async def more_page(request: Request, panel: AnyPanel) -> Response:
    """Phone menu: every section that does not fit the bottom bar."""
    return render(request, "panel/more.html", panel, active="more")


@router.get("/admin/{studio_id}/account")
async def account_page(request: Request, panel: AnyPanel) -> Response:
    return render(request, "panel/account.html", panel, active="account")
