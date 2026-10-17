"""Panel users, their roles per studio, and server-side sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.catalog import studio_fk
from app.models.enums import Role, enum_column


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    # Emails are stored lowercased by the auth service; the constraint keeps it that way.
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudioMembership(IdMixin, TimestampMixin, Base):
    """A user's role in one studio. A master account can be linked to their staff record."""

    __tablename__ = "studio_memberships"
    __table_args__ = (
        UniqueConstraint("studio_id", "user_id"),
        ForeignKeyConstraint(["studio_id", "staff_id"], ["staff.studio_id", "staff.id"], ondelete="RESTRICT"),
    )

    studio_id: Mapped[int] = studio_fk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(enum_column(Role, "membership_role"))
    staff_id: Mapped[int | None] = mapped_column(BigInteger)


class UserSession(IdMixin, Base):
    """Only hashes of the session and CSRF tokens are stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
