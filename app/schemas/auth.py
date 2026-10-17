from __future__ import annotations

from pydantic import Field

from app.models.enums import Role
from app.schemas.common import Schema


class LoginIn(Schema):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeIn(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MembershipOut(Schema):
    studio_id: int
    studio_slug: str
    studio_name: str
    role: Role


class MeOut(Schema):
    id: int
    email: str
    full_name: str
    memberships: list[MembershipOut]
