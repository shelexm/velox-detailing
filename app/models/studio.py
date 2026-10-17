from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Studio(IdMixin, TimestampMixin, Base):
    """A detailing studio (tenant). Every studio-owned row references studios.id."""

    __tablename__ = "studios"

    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
