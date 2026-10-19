"""Panel login and logout. Sessions live in the database; the browser keeps an HttpOnly cookie."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentAuth, DbSession, check_same_origin, client_ip
from app.core import security
from app.core.errors import RateLimitedError, UnauthorizedError
from app.schemas.auth import LoginIn, MembershipOut, MeOut, PasswordChangeIn
from app.services import auth as auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _set_cookies(response: Response, request: Request, token: str, csrf_token: str, max_age: int) -> None:
    secure = bool(request.app.state.settings.cookie_secure)
    response.set_cookie(
        security.SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/"
    )
    # Readable by the panel's JavaScript, which echoes it in the X-CSRF-Token header.
    response.set_cookie(
        security.CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False, secure=secure, samesite="strict", path="/"
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    response.delete_cookie(security.CSRF_COOKIE, path="/")


async def _me(session: DbSession, user_id: int, email: str, full_name: str) -> MeOut:
    rows = await auth_service.memberships(session, user_id)
    return MeOut(
        id=user_id,
        email=email,
        full_name=full_name,
        memberships=[
            MembershipOut(studio_id=s.id, studio_slug=s.slug, studio_name=s.name, role=m.role) for m, s in rows
        ],
    )


@router.post("/login")
async def login(payload: LoginIn, request: Request, response: Response, session: DbSession) -> MeOut:
    check_same_origin(request)
    limiters = request.app.state.limiters
    email, ip = auth_service.normalize_email(payload.email), client_ip(request)
    pair = f"{email}|{ip}"
    if (
        limiters.login_by_email_and_ip.is_blocked(pair)
        or limiters.login_by_email.is_blocked(email)
        or limiters.login_by_ip.is_blocked(ip)
    ):
        raise RateLimitedError("Слишком много попыток входа. Попробуйте через 15 минут")
    try:
        user = await auth_service.authenticate(session, email, payload.password)
    except UnauthorizedError:
        limiters.login_by_email_and_ip.hit(pair)
        limiters.login_by_email.hit(email)
        limiters.login_by_ip.hit(ip)
        raise
    limiters.login_by_email_and_ip.reset(pair)
    limiters.login_by_email.reset(email)
    ttl = timedelta(hours=request.app.state.settings.session_ttl_hours)
    issued = await auth_service.start_session(session, user, ttl)
    _set_cookies(response, request, issued.token, issued.csrf_token, int(ttl.total_seconds()))
    return await _me(session, user.id, user.email, user.full_name)


@router.post("/logout", status_code=204)
async def logout(auth: CurrentAuth, session: DbSession, response: Response) -> Response:
    await auth_service.revoke_session(session, auth.session_row)
    response.status_code = 204
    _clear_cookies(response)
    return response


@router.post("/password", status_code=204)
async def change_password(
    payload: PasswordChangeIn, auth: CurrentAuth, session: DbSession, request: Request
) -> Response:
    limiter = request.app.state.limiters.login_by_ip
    ip = client_ip(request)
    if limiter.is_blocked(ip):
        raise RateLimitedError("Слишком много попыток. Попробуйте через 15 минут")
    try:
        await auth_service.change_password(
            session, auth.user, auth.session_row, payload.current_password, payload.new_password
        )
    except Exception:
        limiter.hit(ip)
        raise
    return Response(status_code=204)


@router.get("/me")
async def me(auth: CurrentAuth, session: DbSession) -> MeOut:
    return await _me(session, auth.user.id, auth.user.email, auth.user.full_name)
