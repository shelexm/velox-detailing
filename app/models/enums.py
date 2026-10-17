"""String enums stored as VARCHAR with CHECK constraints (no native PostgreSQL enum types to migrate)."""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa


class BookingStatus(StrEnum):
    HOLD = "hold"  # time held while the client finishes the bot flow
    NEW = "new"
    CONFIRMED = "confirmed"
    DONE = "done"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    EXPIRED = "expired"  # a hold that was never completed


# Statuses that occupy a box and a master; must match the EXCLUDE constraints in the migration.
ACTIVE_BOOKING_STATUSES = (BookingStatus.HOLD, BookingStatus.NEW, BookingStatus.CONFIRMED)


class BookingSource(StrEnum):
    SITE = "site"
    TELEGRAM = "telegram"
    ADMIN = "admin"
    PHONE = "phone"


class StaffSelection(StrEnum):
    CLIENT = "client"  # the client may pick a master (or "any")
    STUDIO = "studio"  # the studio assigns the master


class ServiceKind(StrEnum):
    SERVICE = "service"
    PACKAGE = "package"
    INSPECTION = "inspection"


class SpecialDayKind(StrEnum):
    CLOSED = "closed"
    SHORT = "short"


class AbsenceKind(StrEnum):
    VACATION = "vacation"
    SICK = "sick"
    DAY_OFF = "day_off"


class ActorType(StrEnum):
    USER = "user"
    CLIENT = "client"
    BOT = "bot"
    SYSTEM = "system"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"  # will be retried
    DEAD = "dead"  # gave up after the retry limit
    SKIPPED = "skipped"  # nothing to deliver (no chat configured)


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MASTER = "master"


def enum_column(enum: type[StrEnum], name: str) -> sa.Enum:
    return sa.Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda members: [member.value for member in members],
    )
