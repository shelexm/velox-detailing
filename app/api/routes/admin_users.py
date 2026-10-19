"""Panel access for the owner: who can sign in to this studio and with which role.

There is no public registration. The owner adds a person by e-mail; a new account gets a temporary
password that is shown once to the owner (it is never stored in clear or logged) and should be changed
on the account page after the first sign-in.
"""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import Field, field_validator
from sqlalchemy import func, select

from app.api.deps import DbSession, Owner
from app.core import security
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import Staff, StudioMembership, User
from app.models.enums import Role
from app.schemas.common import Schema
from app.services.auth import normalize_email, revoke_all_sessions

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}/users", tags=["admin-users"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MemberCreateIn(Schema):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    role: Role = Role.ADMIN
    staff_id: int | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = normalize_email(value)
        if not EMAIL.match(value):
            raise ValueError("Некорректный e-mail")
        return value

    @field_validator("full_name", mode="before")
    @classmethod
    def _name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class MemberUpdateIn(Schema):
    role: Role | None = None
    staff_id: int | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=120)


def _temporary_password() -> str:
    return secrets.token_urlsafe(12)


async def _own_account_only(session, studio_id: int, user_id: int) -> None:
    """Password and name belong to the account, not to the studio: refuse when the person works elsewhere too."""
    elsewhere = await session.scalar(
        select(func.count())
        .select_from(StudioMembership)
        .where(StudioMembership.user_id == user_id, StudioMembership.studio_id != studio_id)
    )
    if elsewhere:
        raise ConflictError(
            "Этот аккаунт есть и в других студиях: пароль и имя меняет сам человек на странице учётной записи",
            code="shared_account",
        )


async def _staff_ok(session, studio_id: int, staff_id: int | None) -> None:
    if staff_id is None:
        return
    if await session.scalar(select(Staff.id).where(Staff.studio_id == studio_id, Staff.id == staff_id)) is None:
        raise ValidationFailedError(details=[{"field": "staff_id", "message": "Мастер не найден"}])


async def _membership(session, studio_id: int, user_id: int) -> StudioMembership:
    row = await session.scalar(
        select(StudioMembership).where(StudioMembership.studio_id == studio_id, StudioMembership.user_id == user_id)
    )
    if row is None:
        raise NotFoundError("Сотрудник не найден")
    return row


async def _owners(session, studio_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).where(StudioMembership.studio_id == studio_id, StudioMembership.role == Role.OWNER)
        )
        or 0
    )


@router.post("", status_code=201)
async def add_member(payload: MemberCreateIn, access: Owner, session: DbSession) -> dict:
    sid = access.studio.id
    await _staff_ok(session, sid, payload.staff_id)
    user = await session.scalar(select(User).where(User.email == payload.email))
    temporary = None
    if user is None:
        temporary = _temporary_password()
        user = User(
            email=payload.email,
            full_name=payload.full_name,
            password_hash=security.hash_password(temporary),
            is_active=True,
        )
        session.add(user)
        await session.flush()
    elif await session.scalar(
        select(StudioMembership.id).where(StudioMembership.studio_id == sid, StudioMembership.user_id == user.id)
    ):
        raise ConflictError("У этого e-mail уже есть доступ к студии", code="member_exists")
    session.add(
        StudioMembership(
            studio_id=sid,
            user_id=user.id,
            role=payload.role,
            staff_id=payload.staff_id if payload.role == Role.MASTER else None,
        )
    )
    await session.commit()
    # An existing account keeps its own password: it simply gets one more studio.
    return {"user_id": user.id, "email": user.email, "temporary_password": temporary}


@router.patch("/{user_id}")
async def update_member(user_id: int, payload: MemberUpdateIn, access: Owner, session: DbSession) -> dict:
    sid = access.studio.id
    membership = await _membership(session, sid, user_id)
    values = payload.model_dump(exclude_unset=True)
    if "role" in values and values["role"] is not None and values["role"] != membership.role:
        if membership.role == Role.OWNER and await _owners(session, sid) <= 1:
            raise ConflictError("Нужен хотя бы один владелец студии", code="last_owner")
        membership.role = values["role"]
    if "staff_id" in values:
        await _staff_ok(session, sid, values["staff_id"])
        membership.staff_id = values["staff_id"]
    if membership.role != Role.MASTER:
        membership.staff_id = None
    if values.get("full_name"):
        await _own_account_only(session, sid, user_id)
        user = await session.get(User, user_id)
        user.full_name = " ".join(values["full_name"].split())
    await session.commit()
    return {"user_id": user_id, "role": membership.role, "staff_id": membership.staff_id}


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: int, access: Owner, session: DbSession) -> dict:
    """New temporary password; the person is signed out everywhere."""
    await _membership(session, access.studio.id, user_id)
    if user_id == access.user.id:
        raise ValidationFailedError("Свой пароль меняйте на странице учётной записи")
    await _own_account_only(session, access.studio.id, user_id)
    user = await session.get(User, user_id)
    temporary = _temporary_password()
    user.password_hash = security.hash_password(temporary)
    await revoke_all_sessions(session, user_id)
    await session.commit()
    return {"user_id": user_id, "temporary_password": temporary}


@router.delete("/{user_id}", status_code=204)
async def remove_member(user_id: int, access: Owner, session: DbSession) -> Response:
    sid = access.studio.id
    membership = await _membership(session, sid, user_id)
    if user_id == access.user.id:
        raise ConflictError("Нельзя закрыть доступ самому себе", code="self_removal")
    if membership.role == Role.OWNER and await _owners(session, sid) <= 1:
        raise ConflictError("Нужен хотя бы один владелец студии", code="last_owner")
    await session.delete(membership)
    remaining = await session.scalar(select(func.count()).where(StudioMembership.user_id == user_id))
    if not remaining:
        # No studio left: the account can no longer sign in anywhere.
        await revoke_all_sessions(session, user_id)
    await session.commit()
    return Response(status_code=204)
