"""Panel users: login, sessions, logout, and creating the first administrator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import UnauthorizedError, ValidationFailedError
from app.models import Studio, StudioMembership, User, UserSession
from app.models.enums import Role

LAST_SEEN_RESOLUTION = timedelta(minutes=5)


@dataclass
class IssuedSession:
    user: User
    token: str
    csrf_token: str
    expires_at: datetime


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    """Same error and similar timing whether the e-mail is unknown, inactive or the password is wrong."""
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    valid = security.verify_password(user.password_hash if user else None, password)
    if user is None or not valid or not user.is_active:
        raise UnauthorizedError("Неверный e-mail или пароль", code="invalid_credentials")
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    return user


async def start_session(
    session: AsyncSession, user: User, ttl: timedelta, now: datetime | None = None
) -> IssuedSession:
    now = now or datetime.now(UTC)
    token, csrf_token = security.new_token(), security.new_token()
    expires_at = now + ttl
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=security.token_hash(token),
            csrf_hash=security.token_hash(csrf_token),
            expires_at=expires_at,
            last_seen_at=now,
        )
    )
    user.last_login_at = now
    await session.commit()
    return IssuedSession(user=user, token=token, csrf_token=csrf_token, expires_at=expires_at)


async def resolve_session(
    session: AsyncSession, token: str | None, now: datetime | None = None
) -> tuple[User, UserSession] | None:
    if not token:
        return None
    now = now or datetime.now(UTC)
    row = await session.scalar(select(UserSession).where(UserSession.token_hash == security.token_hash(token)))
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    if row.last_seen_at is None or now - row.last_seen_at > LAST_SEEN_RESOLUTION:
        row.last_seen_at = now
        await session.commit()
    return user, row


async def revoke_session(session: AsyncSession, row: UserSession, now: datetime | None = None) -> None:
    row.revoked_at = now or datetime.now(UTC)
    await session.commit()


async def revoke_all_sessions(session: AsyncSession, user_id: int, now: datetime | None = None) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now or datetime.now(UTC))
    )


async def change_password(
    session: AsyncSession, user: User, current_session: UserSession, current: str, new: str
) -> None:
    """Checks the current password, stores the new one and signs out every other device."""
    if not security.verify_password(user.password_hash, current):
        raise ValidationFailedError(details=[{"field": "current_password", "message": "Неверный текущий пароль"}])
    try:
        security.validate_new_password(new)
    except ValueError as exc:
        raise ValidationFailedError(details=[{"field": "new_password", "message": str(exc)}]) from exc
    if security.verify_password(user.password_hash, new):
        raise ValidationFailedError(details=[{"field": "new_password", "message": "Новый пароль совпадает с текущим"}])
    user.password_hash = security.hash_password(new)
    now = datetime.now(UTC)
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.id != current_session.id)
        .values(revoked_at=now)
    )
    await session.commit()


async def memberships(session: AsyncSession, user_id: int) -> list[tuple[StudioMembership, Studio]]:
    rows = await session.execute(
        select(StudioMembership, Studio)
        .join(Studio, Studio.id == StudioMembership.studio_id)
        .where(StudioMembership.user_id == user_id)
        .order_by(Studio.id)
    )
    return [(membership, studio) for membership, studio in rows.all()]


async def create_or_update_admin(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    password: str,
    studio_slug: str,
    role: Role = Role.OWNER,
    reset_password: bool = False,
) -> tuple[User, bool]:
    """Used by the CLI bootstrap. Returns the user and whether it was created."""
    security.validate_new_password(password)
    studio = await session.scalar(select(Studio).where(Studio.slug == studio_slug))
    if studio is None:
        raise ValueError(f"Студия '{studio_slug}' не найдена. Сначала выполните: python -m app.cli seed")
    email = normalize_email(email)
    if "@" not in email:
        raise ValueError("Некорректный e-mail")
    user = await session.scalar(select(User).where(User.email == email))
    created = user is None
    if user is None:
        user = User(email=email, full_name=full_name, password_hash=security.hash_password(password), is_active=True)
        session.add(user)
        await session.flush()
    elif reset_password:
        user.password_hash = security.hash_password(password)
        user.is_active = True
        await revoke_all_sessions(session, user.id)
    else:
        raise ValueError("Пользователь уже существует. Чтобы сменить пароль, добавьте --reset-password")
    membership = await session.scalar(
        select(StudioMembership).where(StudioMembership.studio_id == studio.id, StudioMembership.user_id == user.id)
    )
    if membership is None:
        session.add(StudioMembership(studio_id=studio.id, user_id=user.id, role=role))
    else:
        membership.role = role
    await session.commit()
    return user, created
