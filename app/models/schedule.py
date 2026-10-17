"""Studio working hours, breaks, special days, masters' hours, absences and time blocks."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.catalog import studio_fk
from app.models.enums import AbsenceKind, SpecialDayKind, enum_column


class StudioHours(Base):
    """Weekly hours; weekday 0 = Monday."""

    __tablename__ = "studio_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("NOT is_open OR closes_at > opens_at", name="open_before_close"),
        ForeignKeyConstraint(["studio_id"], ["studios.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    opens_at: Mapped[time] = mapped_column(Time)
    closes_at: Mapped[time] = mapped_column(Time)


class StudioBreak(IdMixin, Base):
    """A daily break (no booking starts inside it), e.g. lunch 13:00-13:30 on weekdays."""

    __tablename__ = "studio_breaks"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("ends_at > starts_at", name="start_before_end"),
    )

    studio_id: Mapped[int] = studio_fk()
    weekday: Mapped[int] = mapped_column(SmallInteger)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)


class SpecialDay(IdMixin, Base):
    """A date that overrides the weekly hours: closed or shortened."""

    __tablename__ = "special_days"
    __table_args__ = (
        UniqueConstraint("studio_id", "day"),
        CheckConstraint(
            "kind = 'closed' OR (opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)",
            name="short_day_hours",
        ),
    )

    studio_id: Mapped[int] = studio_fk()
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[SpecialDayKind] = mapped_column(enum_column(SpecialDayKind, "special_day_kind"))
    opens_at: Mapped[time | None] = mapped_column(Time)
    closes_at: Mapped[time | None] = mapped_column(Time)
    note: Mapped[str | None] = mapped_column(String(200))


class StaffHours(Base):
    """A master's weekly schedule; it cannot exceed the studio hours (checked by the service layer)."""

    __tablename__ = "staff_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("NOT is_working OR ends_at > starts_at", name="start_before_end"),
        ForeignKeyConstraint(["studio_id", "staff_id"], ["staff.studio_id", "staff.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = mapped_column(BigInteger)
    staff_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)


class StaffAbsence(IdMixin, TimestampMixin, Base):
    __tablename__ = "staff_absences"
    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="range"),
        ForeignKeyConstraint(["studio_id", "staff_id"], ["staff.studio_id", "staff.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = studio_fk()
    staff_id: Mapped[int] = mapped_column(BigInteger, index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    kind: Mapped[AbsenceKind] = mapped_column(enum_column(AbsenceKind, "absence_kind"), default=AbsenceKind.VACATION)
    note: Mapped[str | None] = mapped_column(String(200))


class TimeBlock(IdMixin, TimestampMixin, Base):
    """Blocked time for the whole studio, one box or one master (training, deliveries...)."""

    __tablename__ = "time_blocks"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="start_before_end"),
        ForeignKeyConstraint(["studio_id", "resource_id"], ["resources.studio_id", "resources.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["studio_id", "staff_id"], ["staff.studio_id", "staff.id"], ondelete="CASCADE"),
    )

    studio_id: Mapped[int] = studio_fk()
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    staff_id: Mapped[int | None] = mapped_column(BigInteger)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200))
