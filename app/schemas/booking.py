from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from app.models.enums import BookingSource, BookingStatus, ServiceKind, StaffSelection
from app.schemas.common import Schema


class StudioPublicOut(Schema):
    slug: str
    name: str
    timezone: str
    city: str | None = None
    address: str | None = None
    address_note: str | None = None
    route_url: str | None = None
    phone: str | None = None
    whatsapp_url: str | None = None
    telegram_bot_username: str | None = None
    email: str | None = None
    schedule_text: str | None = None
    legal_name: str | None = None
    inn: str | None = None
    online_booking_enabled: bool
    slot_step_minutes: int
    horizon_days: int


class StaffPublicOut(Schema):
    id: int
    short_name: str
    full_name: str
    title: str | None = None
    specializations: list[str] = Field(default_factory=list)
    initials: str


class ServicePublicOut(Schema):
    id: int
    slug: str
    kind: ServiceKind
    name: str
    short_description: str
    price_from: int | None
    duration_label: str | None
    duration_minutes: int | None
    duration_days: int | None
    group_slug: str | None = None
    group_title: str | None = None
    staff_selection: StaffSelection
    staff: list[StaffPublicOut] = Field(default_factory=list)
    badge: str | None = None
    note: str | None = None
    items: list[str] = Field(default_factory=list)


class SlotOut(Schema):
    start: datetime
    end: datetime
    available: bool
    free_places: int
    total_places: int
    blocked: bool = False


class DayOut(Schema):
    date: date
    open: bool
    slots: list[SlotOut]


class AvailabilityOut(Schema):
    service_id: int
    timezone: str
    days: list[DayOut]


class BookingCreateIn(Schema):
    service_id: int = Field(ge=1)
    starts_at: datetime
    staff_id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=32)
    vehicle: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=1000)
    consent: bool = False
    # Honeypot: hidden on the form, bots fill it in.
    website: str | None = Field(default=None, max_length=200)


class BookingCreatedOut(Schema):
    number: int
    status: BookingStatus
    service_name: str
    starts_at: datetime
    ends_at: datetime
    staff_name: str | None
    price_from: int | None
    duration_label: str | None
    manage_url: str
    calendar_url: str


class BookingManageOut(Schema):
    number: int
    status: BookingStatus
    service_name: str
    starts_at: datetime
    ends_at: datetime
    staff_name: str | None
    price_from: int | None
    can_cancel: bool
    cancel_deadline_hours: int


# ----- admin -----


class BookingAdminOut(Schema):
    id: int
    number: int
    status: BookingStatus
    source: BookingSource
    service_id: int
    service_name: str
    staff_id: int | None
    staff_name: str | None
    resource_id: int | None
    resource_name: str | None
    starts_at: datetime
    ends_at: datetime
    client_id: int | None
    client_name: str | None
    contact_name: str | None
    phone: str | None
    telegram_username: str | None
    vehicle: str | None
    client_comment: str | None
    internal_note: str | None
    price_from: int | None
    created_at: datetime
    version: int


class BookingEventOut(Schema):
    kind: str
    from_status: str | None
    to_status: str | None
    actor_type: str
    actor_name: str | None
    data: dict
    created_at: datetime


class BookingDetailOut(BookingAdminOut):
    events: list[BookingEventOut]
    client_visits: int


class BookingAdminCreateIn(Schema):
    service_id: int = Field(ge=1)
    starts_at: datetime
    staff_id: int | None = Field(default=None, ge=1)
    contact_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=32)
    vehicle: str | None = Field(default=None, max_length=120)
    client_comment: str | None = Field(default=None, max_length=1000)
    internal_note: str | None = Field(default=None, max_length=2000)
    status: BookingStatus = BookingStatus.CONFIRMED
    source: BookingSource = BookingSource.ADMIN

    @field_validator("status")
    @classmethod
    def _initial_status(cls, value: BookingStatus) -> BookingStatus:
        if value not in (BookingStatus.NEW, BookingStatus.CONFIRMED):
            raise ValueError("Новая запись может быть только новой или подтверждённой")
        return value

    @field_validator("source")
    @classmethod
    def _studio_source(cls, value: BookingSource) -> BookingSource:
        if value not in (BookingSource.ADMIN, BookingSource.PHONE):
            raise ValueError("Источник записи из панели: admin или phone")
        return value


class BookingUpdateIn(Schema):
    contact_name: str | None = Field(default=None, max_length=120)
    vehicle: str | None = Field(default=None, max_length=120)
    client_comment: str | None = Field(default=None, max_length=1000)
    internal_note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class StatusChangeIn(Schema):
    status: BookingStatus
    reason: str | None = Field(default=None, max_length=300)
    version: int | None = None


class RescheduleIn(Schema):
    starts_at: datetime
    service_id: int | None = Field(default=None, ge=1)
    staff_id: int | None = Field(default=None, ge=1)
    version: int | None = None


class ClientListItemOut(Schema):
    id: int
    full_name: str
    phone: str
    vehicles: list[str]
    visits: int
    last_visit: datetime | None
    next_booking: datetime | None
    tags: list[str]
    created_at: datetime


class ClientListOut(Schema):
    total: int
    items: list[ClientListItemOut]
    counts: dict[str, int]


class ClientVisitOut(Schema):
    booking_id: int
    number: int
    service_name: str
    starts_at: datetime
    status: BookingStatus
    staff_name: str | None


class ClientDetailOut(ClientListItemOut):
    notes: str | None
    telegram_username: str | None
    reminders_enabled: bool
    consent_at: datetime | None
    history: list[ClientVisitOut]


class ClientUpdateIn(Schema):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=12)
    reminders_enabled: bool | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [" ".join(t.split())[:40] for t in value if t and t.strip()]
        return list(dict.fromkeys(cleaned))
