"""Request dependencies: current user, CSRF check, studio membership and role checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Path, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.ratelimit import Limiters
from app.db.session import get_session
from app.models import Studio, StudioMembership, User, UserSession
from app.models.enums import ActorType, Role
from app.services.auth import resolve_session
from app.services.booking import Actor

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
STAFF_ROLES = (Role.OWNER, Role.ADMIN, Role.MASTER)
MANAGER_ROLES = (Role.OWNER, Role.ADMIN)
OWNER_ROLES = (Role.OWNER,)

DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_limiters(request: Request) -> Limiters:
    return request.app.state.limiters


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_same_origin(request: Request) -> None:
    """Browsers send Origin on cross-site POSTs; refuse any that does not match this host."""
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise ForbiddenError("Запрос отклонён", code="bad_origin")


@dataclass
class AuthContext:
    user: User
    session_row: UserSession


async def current_auth(request: Request, session: DbSession) -> AuthContext:
    resolved = await resolve_session(session, request.cookies.get(security.SESSION_COOKIE))
    if resolved is None:
        raise UnauthorizedError()
    user, row = resolved
    if request.method not in SAFE_METHODS:
        check_same_origin(request)
        if not security.tokens_match(request.headers.get(security.CSRF_HEADER), row.csrf_hash):
            raise ForbiddenError("Сессия устарела. Обновите страницу", code="csrf_failed")
    return AuthContext(user=user, session_row=row)


CurrentAuth = Annotated[AuthContext, Depends(current_auth)]


@dataclass
class StudioAccess:
    studio: Studio
    membership: StudioMembership
    user: User

    @property
    def actor(self) -> Actor:
        return Actor(ActorType.USER, user_id=self.user.id)

    @property
    def is_master_only(self) -> bool:
        return self.membership.role == Role.MASTER


def studio_access(*roles: Role):
    """Membership in the studio from the path; a non-member gets 404 so studio ids cannot be probed."""

    async def dependency(auth: CurrentAuth, session: DbSession, studio_id: Annotated[int, Path(ge=1)]) -> StudioAccess:
        membership = await session.scalar(
            select(StudioMembership).where(
                StudioMembership.studio_id == studio_id, StudioMembership.user_id == auth.user.id
            )
        )
        if membership is None:
            raise NotFoundError("Студия не найдена")
        if membership.role not in roles:
            raise ForbiddenError()
        studio = await session.get(Studio, studio_id)
        if studio is None:
            raise NotFoundError("Студия не найдена")
        return StudioAccess(studio=studio, membership=membership, user=auth.user)

    return dependency


async def public_studio(session: DbSession, slug: Annotated[str, Path(max_length=64)]) -> Studio:
    studio = await session.scalar(select(Studio).where(Studio.slug == slug))
    if studio is None:
        raise NotFoundError("Студия не найдена")
    return studio


PublicStudio = Annotated[Studio, Depends(public_studio)]
AnyMember = Annotated[StudioAccess, Depends(studio_access(*STAFF_ROLES))]
Manager = Annotated[StudioAccess, Depends(studio_access(*MANAGER_ROLES))]
Owner = Annotated[StudioAccess, Depends(studio_access(*OWNER_ROLES))]
