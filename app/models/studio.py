from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Studio(IdMixin, TimestampMixin, Base):
    """A detailing studio (tenant). Every studio-owned row references studios.id."""

    __tablename__ = "studios"
    __table_args__ = (
        CheckConstraint("slot_step_minutes IN (15, 30, 60, 120)", name="slot_step"),
        CheckConstraint("buffer_minutes BETWEEN 0 AND 240", name="buffer"),
        CheckConstraint("min_lead_minutes BETWEEN 0 AND 10080", name="min_lead"),
        CheckConstraint("horizon_days BETWEEN 1 AND 365", name="horizon"),
        CheckConstraint("cancel_deadline_hours BETWEEN 0 AND 720", name="cancel_deadline"),
        CheckConstraint("hold_minutes BETWEEN 1 AND 60", name="hold"),
    )

    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")

    # Public contacts and requisites. Empty values are simply not shown on the site.
    city: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(300))
    address_note: Mapped[str | None] = mapped_column(String(300))
    route_url: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(32))
    whatsapp_url: Mapped[str | None] = mapped_column(String(300))
    telegram_bot_username: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(254))
    schedule_text: Mapped[str | None] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(300))
    inn: Mapped[str | None] = mapped_column(String(12))

    # Online booking rules (admin "Слоты" screen).
    online_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    slot_step_minutes: Mapped[int] = mapped_column(Integer, default=60)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    min_lead_minutes: Mapped[int] = mapped_column(Integer, default=120)
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    cancel_deadline_hours: Mapped[int] = mapped_column(Integer, default=24)
    hold_minutes: Mapped[int] = mapped_column(Integer, default=10)
    respect_staff_availability: Mapped[bool] = mapped_column(Boolean, default=True)

    telegram_admin_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    # Last issued booking number; incremented under a row lock, which also serializes booking allocation.
    booking_seq: Mapped[int] = mapped_column(Integer, default=1000)
