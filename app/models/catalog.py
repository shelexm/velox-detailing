"""Staff, boxes, service categories, services and the landing page service groups."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ServiceKind, StaffSelection, enum_column


def studio_fk() -> Mapped[int]:
    return mapped_column(BigInteger, ForeignKey("studios.id", ondelete="CASCADE"), index=True)


class Staff(IdMixin, TimestampMixin, Base):
    """A master. One master works on one car at a time (enforced on bookings)."""

    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("studio_id", "id"),)

    studio_id: Mapped[int] = studio_fk()
    full_name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(120))
    specializations: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list)
    # False: the client cannot pick this master online, only the studio assigns them.
    client_selectable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)


class Resource(IdMixin, TimestampMixin, Base):
    """A place for one car (a box). The number of active resources is the studio capacity."""

    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("studio_id", "id"),)

    studio_id: Mapped[int] = studio_fk()
    name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ServiceCategory(IdMixin, Base):
    __tablename__ = "service_categories"
    __table_args__ = (UniqueConstraint("studio_id", "id"), UniqueConstraint("studio_id", "slug"))

    studio_id: Mapped[int] = studio_fk()
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ServiceGroup(IdMixin, TimestampMixin, Base):
    """A direction shown as a card on the landing page with its own detail page (e.g. "Полировка кузова")."""

    __tablename__ = "service_groups"
    __table_args__ = (UniqueConstraint("studio_id", "id"), UniqueConstraint("studio_id", "slug"))

    studio_id: Mapped[int] = studio_fk()
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str | None] = mapped_column(String(300))
    features: Mapped[list[str]] = mapped_column(JSONB, default=list)
    price_label: Mapped[str | None] = mapped_column(String(60))
    duration_label: Mapped[str | None] = mapped_column(String(60))
    badge: Mapped[str | None] = mapped_column(String(40))
    is_wide: Mapped[bool] = mapped_column(Boolean, default=False)
    # Detail page: eyebrow, description, includes (list), guarantee, upsell, footnote.
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    image_id: Mapped[int | None] = mapped_column(BigInteger)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Service(IdMixin, TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("studio_id", "id"),
        UniqueConstraint("studio_id", "slug"),
        CheckConstraint("(duration_minutes IS NOT NULL) <> (duration_days IS NOT NULL)", name="exactly_one_duration"),
        CheckConstraint("duration_minutes IS NULL OR duration_minutes BETWEEN 5 AND 1440", name="duration_minutes"),
        CheckConstraint("duration_days IS NULL OR duration_days BETWEEN 1 AND 30", name="duration_days"),
        CheckConstraint("price_from IS NULL OR price_from >= 0", name="price_non_negative"),
        CheckConstraint("char_length(short_description) <= 160", name="short_description_length"),
        ForeignKeyConstraint(
            ["studio_id", "category_id"],
            ["service_categories.studio_id", "service_categories.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["studio_id", "group_id"], ["service_groups.studio_id", "service_groups.id"], ondelete="RESTRICT"
        ),
    )

    studio_id: Mapped[int] = studio_fk()
    category_id: Mapped[int | None] = mapped_column(BigInteger)
    group_id: Mapped[int | None] = mapped_column(BigInteger)
    slug: Mapped[str] = mapped_column(String(64))
    kind: Mapped[ServiceKind] = mapped_column(enum_column(ServiceKind, "service_kind"), default=ServiceKind.SERVICE)
    name: Mapped[str] = mapped_column(String(120))
    short_description: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list[str]] = mapped_column(JSONB, default=list)  # package composition
    price_from: Mapped[int | None] = mapped_column(Integer)  # rubles
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    duration_label: Mapped[str | None] = mapped_column(String(40))
    badge: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(300))
    online_booking: Mapped[bool] = mapped_column(Boolean, default=True)
    staff_selection: Mapped[StaffSelection] = mapped_column(
        enum_column(StaffSelection, "staff_selection"), default=StaffSelection.CLIENT
    )
    requires_resource: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_staff: Mapped[bool] = mapped_column(Boolean, default=True)
    show_in_price_list: Mapped[bool] = mapped_column(Boolean, default=True)
    image_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ServiceStaff(Base):
    """Which masters perform a service."""

    __tablename__ = "service_staff"
    __table_args__ = (
        ForeignKeyConstraint(["studio_id", "service_id"], ["services.studio_id", "services.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["studio_id", "staff_id"], ["staff.studio_id", "staff.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = studio_fk()
    service_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
