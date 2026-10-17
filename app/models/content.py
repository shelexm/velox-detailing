"""Site content managed in the panel: media library, before/after cases, reviews, gift options, page sections."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.catalog import studio_fk


class MediaAsset(IdMixin, TimestampMixin, Base):
    """An image in the studio media library. Files live under MEDIA_ROOT/<studio_id>/<storage_key>/."""

    __tablename__ = "media_assets"
    __table_args__ = (UniqueConstraint("studio_id", "id"), UniqueConstraint("storage_key"))

    studio_id: Mapped[int] = studio_fk()
    storage_key: Mapped[str] = mapped_column(String(40))
    original_name: Mapped[str | None] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # [{"format": "avif", "width": 960, "file": "w960.avif", "bytes": 81234}, ...]
    variants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    alt: Mapped[str] = mapped_column(String(300), default="")
    title: Mapped[str | None] = mapped_column(String(200))
    # Provenance: where a third-party image comes from and under which licence it is used.
    source_url: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(200))
    author_url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(120))
    license_url: Mapped[str | None] = mapped_column(String(500))
    is_example: Mapped[bool] = mapped_column(Boolean, default=False)
    seed_key: Mapped[str | None] = mapped_column(String(80))  # stable id of images created by the seed
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class PortfolioCase(IdMixin, TimestampMixin, Base):
    """A before/after comparison in the "Работы" block."""

    __tablename__ = "portfolio_cases"

    studio_id: Mapped[int] = studio_fk()
    title: Mapped[str] = mapped_column(String(120))
    short_title: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(String(400))
    car: Mapped[str | None] = mapped_column(String(120))
    works: Mapped[str | None] = mapped_column(String(200))
    term: Mapped[str | None] = mapped_column(String(60))
    before_label: Mapped[str] = mapped_column(String(30), default="ДО")
    after_label: Mapped[str] = mapped_column(String(30), default="ПОСЛЕ")
    before_image_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("media_assets.id", ondelete="SET NULL"))
    after_image_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("media_assets.id", ondelete="SET NULL"))
    # Not the studio's own work (stock or illustration): the site shows the "Примеры работ" label.
    is_example: Mapped[bool] = mapped_column(Boolean, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Review(IdMixin, TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),)

    studio_id: Mapped[int] = studio_fk()
    author_name: Mapped[str | None] = mapped_column(String(120))
    car: Mapped[str | None] = mapped_column(String(120))
    service_label: Mapped[str | None] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    source_url: Mapped[str | None] = mapped_column(String(500))
    # Sample text from the design: shown with the "ДЕМО" label until replaced.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class GiftOption(IdMixin, TimestampMixin, Base):
    __tablename__ = "gift_options"

    studio_id: Mapped[int] = studio_fk()
    label: Mapped[str] = mapped_column(String(60))
    value_text: Mapped[str] = mapped_column(String(80))
    subtitle: Mapped[str | None] = mapped_column(String(160))
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class SiteSection(Base):
    """One landing page block. `content` is validated by the Pydantic model registered for `key`."""

    __tablename__ = "site_sections"

    studio_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("studios.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
