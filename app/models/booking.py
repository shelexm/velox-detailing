"""Clients, vehicles, bookings, booking history and the notification outbox."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSTZRANGE, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.catalog import studio_fk
from app.models.enums import ActorType, BookingSource, BookingStatus, OutboxStatus, enum_column

ACTIVE_STATUS_SQL = "status IN ('hold', 'new', 'confirmed')"


class Client(IdMixin, TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("studio_id", "id"),
        UniqueConstraint("studio_id", "phone"),
        Index(
            "uq_clients_studio_id_telegram_user_id",
            "studio_id",
            "telegram_user_id",
            unique=True,
            postgresql_where=text("telegram_user_id IS NOT NULL"),
        ),
        CheckConstraint("phone ~ '^\\+7[0-9]{10}$'", name="phone_e164_ru"),
    )

    studio_id: Mapped[int] = studio_fk()
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(16))
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(20))


class Vehicle(IdMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        ForeignKeyConstraint(["studio_id", "client_id"], ["clients.studio_id", "clients.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = studio_fk()
    client_id: Mapped[int] = mapped_column(BigInteger, index=True)
    description: Mapped[str] = mapped_column(String(120))  # "Audi A6, 2021, белый"


class Booking(IdMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("studio_id", "number"),
        UniqueConstraint("studio_id", "id"),
        CheckConstraint("ends_at > starts_at", name="start_before_end"),
        CheckConstraint("occupied_until >= ends_at", name="occupied_after_end"),
        CheckConstraint("status <> 'hold' OR hold_expires_at IS NOT NULL", name="hold_has_expiry"),
        # Active bookings need a client; past ones may be anonymous after the client's data was erased.
        CheckConstraint("client_id IS NOT NULL OR status NOT IN ('new', 'confirmed')", name="client_required"),
        ForeignKeyConstraint(["studio_id", "client_id"], ["clients.studio_id", "clients.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["studio_id", "service_id"], ["services.studio_id", "services.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["studio_id", "staff_id"], ["staff.studio_id", "staff.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["studio_id", "resource_id"], ["resources.studio_id", "resources.id"], ondelete="RESTRICT"
        ),
        # The database itself refuses two active bookings of one master or one box at overlapping times.
        ExcludeConstraint(
            ("staff_id", "="),
            ("occupancy", "&&"),
            name="ex_bookings_staff_overlap",
            using="gist",
            where=text(ACTIVE_STATUS_SQL),
        ),
        ExcludeConstraint(
            ("resource_id", "="),
            ("occupancy", "&&"),
            name="ex_bookings_resource_overlap",
            using="gist",
            where=text(ACTIVE_STATUS_SQL),
        ),
        Index("ix_bookings_studio_id_starts_at", "studio_id", "starts_at"),
        Index("ix_bookings_studio_id_status", "studio_id", "status"),
    )

    studio_id: Mapped[int] = studio_fk()
    number: Mapped[int] = mapped_column(Integer)
    client_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("vehicles.id", ondelete="SET NULL"))
    service_id: Mapped[int] = mapped_column(BigInteger)
    staff_id: Mapped[int | None] = mapped_column(BigInteger)
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # ends_at plus the studio buffer: the box and the master stay busy until then.
    occupied_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occupancy: Mapped[Any] = mapped_column(
        TSTZRANGE, Computed("tstzrange(starts_at, occupied_until, '[)')", persisted=True)
    )
    status: Mapped[BookingStatus] = mapped_column(enum_column(BookingStatus, "booking_status"))
    source: Mapped[BookingSource] = mapped_column(enum_column(BookingSource, "booking_source"))
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_name: Mapped[str | None] = mapped_column(String(120))  # the name given with this request
    vehicle_description: Mapped[str | None] = mapped_column(String(120))
    client_comment: Mapped[str | None] = mapped_column(String(1000))
    internal_note: Mapped[str | None] = mapped_column(String(2000))
    service_name: Mapped[str] = mapped_column(String(120))  # snapshot at booking time
    price_from: Mapped[int | None] = mapped_column(Integer)  # snapshot at booking time
    manage_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    hold_owner: Mapped[str | None] = mapped_column(String(64))  # e.g. "tg:123456" for bot holds
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class BookingEvent(IdMixin, Base):
    """Booking history shown in the admin panel."""

    __tablename__ = "booking_events"
    __table_args__ = (
        ForeignKeyConstraint(["studio_id", "booking_id"], ["bookings.studio_id", "bookings.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = studio_fk()
    booking_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    actor_type: Mapped[ActorType] = mapped_column(enum_column(ActorType, "actor_type"))
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class NotificationOutbox(IdMixin, Base):
    """Transactional outbox: written in the booking transaction, delivered later with retries."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        Index("ix_notification_outbox_status_next_attempt_at", "status", "next_attempt_at"),
        UniqueConstraint("dedupe_key"),
    )

    studio_id: Mapped[int] = studio_fk()
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(40))
    audience: Mapped[str] = mapped_column(String(20))  # "admins" or "client"
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[OutboxStatus] = mapped_column(enum_column(OutboxStatus, "outbox_status"))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_error: Mapped[str | None] = mapped_column(String(500))
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
