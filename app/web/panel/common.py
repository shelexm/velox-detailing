"""Shared pieces of the studio panel pages: access checks, navigation and rendering.

Pages are rendered on the server from the same services as the JSON API; every change goes
through /api/v1/admin/... from the browser (session cookie + CSRF header), so the rules live in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import Depends, Path, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.core import security
from app.core.errors import ForbiddenError, NotFoundError
from app.models import Booking, Studio, StudioMembership, User
from app.models.enums import BookingStatus, Role
from app.services.auth import resolve_session
from app.web.panel import fmt
from app.web.templating import build_templates, render_attrs

templates = build_templates()
templates.env.filters.update(fmt.FILTERS)

ROLE_LABELS = {Role.OWNER: "Владелец", Role.ADMIN: "Администратор", Role.MASTER: "Мастер"}
MANAGERS = (Role.OWNER, Role.ADMIN)


class LoginRequired(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


def login_redirect(request: Request, exc: LoginRequired) -> Response:
    target = "/admin/login"
    if exc.next_path and exc.next_path != "/admin":
        target += f"?next={quote(exc.next_path, safe='/')}"
    return RedirectResponse(target, status_code=303)


@dataclass
class NavItem:
    key: str
    label: str
    icon: str
    href: str
    badge: int | None = None
    mobile: bool = False


@dataclass
class Panel:
    """Who is looking at which studio; available to every panel template as `panel`."""

    user: User
    studio: Studio
    membership: StudioMembership
    memberships: list[tuple[StudioMembership, Studio]] = field(default_factory=list)
    new_count: int = 0

    @property
    def role(self) -> Role:
        return self.membership.role

    @property
    def is_manager(self) -> bool:
        return self.role in MANAGERS

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[self.role]

    @property
    def initials(self) -> str:
        parts = [p for p in (self.user.full_name or self.user.email).replace(".", " ").split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.studio.timezone)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def url(self, path: str = "") -> str:
        return f"/admin/{self.studio.id}{path}"

    @property
    def api(self) -> str:
        return f"/api/v1/admin/studios/{self.studio.id}"

    def nav(self) -> list[NavItem]:
        items = [
            NavItem("dashboard", "Главная", "grid", self.url("/"), mobile=True),
            NavItem("bookings", "Записи", "calendar", self.url("/bookings"), badge=self.new_count or None, mobile=True),
        ]
        if self.is_manager:
            items += [
                NavItem("schedule", "Расписание", "clock", self.url("/schedule")),
                NavItem("services", "Услуги", "drop", self.url("/services")),
                NavItem("staff", "Мастера", "users", self.url("/staff")),
                NavItem("slots", "Слоты", "sliders", self.url("/slots")),
                NavItem("clients", "Клиенты", "client", self.url("/clients"), mobile=True),
            ]
        return items

    def content_nav(self) -> list[NavItem]:
        """Site content screens (not in the mockup, same visual system)."""
        if not self.is_manager:
            return []
        items = [
            NavItem("content", "Контент сайта", "layout", self.url("/content")),
            NavItem("media", "Медиатека", "image", self.url("/media")),
            NavItem("portfolio", "До и после", "compare", self.url("/portfolio")),
            NavItem("reviews", "Отзывы", "quote", self.url("/reviews")),
        ]
        if self.is_owner:
            items += [
                NavItem("settings", "Настройки", "settings", self.url("/settings")),
                NavItem("users", "Доступ", "key", self.url("/users")),
            ]
        return items


async def _new_bookings(session, studio_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(Booking.studio_id == studio_id, Booking.status == BookingStatus.NEW)
        )
        or 0
    )


async def _resolve_user(request: Request, session) -> tuple[User, list[tuple[StudioMembership, Studio]]]:
    from app.services.auth import memberships

    resolved = await resolve_session(session, request.cookies.get(security.SESSION_COOKIE))
    if resolved is None:
        raise LoginRequired(request.url.path)
    user, _row = resolved
    return user, await memberships(session, user.id)


async def panel_user(request: Request, session: DbSession) -> tuple[User, list[tuple[StudioMembership, Studio]]]:
    return await _resolve_user(request, session)


def panel_access(*roles: Role):
    """The signed-in member of the studio in the path; non-members get 404 so ids cannot be probed."""

    async def dependency(request: Request, session: DbSession, studio_id: Annotated[int, Path(ge=1)]) -> Panel:
        user, rows = await _resolve_user(request, session)
        found = next(((m, s) for m, s in rows if s.id == studio_id), None)
        if found is None:
            raise NotFoundError("Студия не найдена")
        membership, studio = found
        if roles and membership.role not in roles:
            raise ForbiddenError("Этот раздел доступен администратору студии")
        return Panel(
            user=user,
            studio=studio,
            membership=membership,
            memberships=rows,
            new_count=await _new_bookings(session, studio.id),
        )

    return dependency


AnyPanel = Annotated[Panel, Depends(panel_access())]
ManagerPanel = Annotated[Panel, Depends(panel_access(*MANAGERS))]
OwnerPanel = Annotated[Panel, Depends(panel_access(Role.OWNER))]


def render(request: Request, template: str, panel: Panel | None, active: str = "", **context: Any) -> HTMLResponse:
    data = {"panel-api": panel.api, "panel-url": panel.url(), "tz": panel.studio.timezone} if panel else {}
    return templates.TemplateResponse(
        request,
        template,
        {"panel": panel, "active": active, "script_data": render_attrs(data), **context},
    )
