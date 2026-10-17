"""Catalog editing from the panel: services, categories, landing directions (service groups)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.models.enums import ServiceKind
from app.schemas.common import Schema

DurationUnit = Literal["minutes", "hours", "days"]


def _strip(value: object) -> object:
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


class ServiceFields(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = None
    group_id: int | None = None
    kind: ServiceKind | None = None
    short_description: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    items: list[str] | None = Field(default=None, max_length=20)
    price_from: int | None = Field(default=None, ge=0, le=10_000_000)
    duration_value: int | None = Field(default=None, ge=1, le=1440)
    duration_unit: DurationUnit | None = None
    duration_label: str | None = Field(default=None, max_length=40)
    badge: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=300)
    online_booking: bool | None = None
    client_selects_staff: bool | None = None
    requires_resource: bool | None = None
    requires_staff: bool | None = None
    show_in_price_list: bool | None = None
    image_id: int | None = None
    staff_ids: list[int] | None = Field(default=None, max_length=50)

    _clean = field_validator("name", "duration_label", "badge", "note", mode="before")(_strip)

    @field_validator("items")
    @classmethod
    def _items(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [" ".join(v.split())[:120] for v in value if v and v.strip()]

    @model_validator(mode="after")
    def _duration_pair(self) -> ServiceFields:
        if (self.duration_value is None) != (self.duration_unit is None):
            raise ValueError("Укажите длительность и единицу измерения")
        if self.duration_unit == "days" and self.duration_value and self.duration_value > 30:
            raise ValueError("Не больше 30 дней")
        if self.duration_unit == "hours" and self.duration_value and self.duration_value > 24:
            raise ValueError("Не больше 24 часов: для дольше используйте дни")
        return self


class ServiceCreateIn(ServiceFields):
    name: str = Field(min_length=1, max_length=120)
    duration_value: int = Field(ge=1, le=1440)
    duration_unit: DurationUnit


class ServiceUpdateIn(ServiceFields):
    pass


class CategoryIn(Schema):
    name: str = Field(min_length=1, max_length=120)

    _clean = field_validator("name", mode="before")(_strip)


class GroupFields(Schema):
    """A direction on the landing page with its own detail page (texts and gallery)."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    short_title: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, max_length=300)
    tagline: str | None = Field(default=None, max_length=120)
    features: list[str] | None = Field(default=None, max_length=8)
    price_label: str | None = Field(default=None, max_length=60)
    duration_label: str | None = Field(default=None, max_length=60)
    badge: str | None = Field(default=None, max_length=40)
    is_wide: bool | None = None
    is_visible: bool | None = None
    image_id: int | None = None
    detail: dict[str, Any] | None = None

    _clean = field_validator(
        "title", "short_title", "tagline", "price_label", "duration_label", "badge", mode="before"
    )(_strip)

    @field_validator("features")
    @classmethod
    def _features(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [" ".join(v.split())[:120] for v in value if v and v.strip()]


class GroupCreateIn(GroupFields):
    title: str = Field(min_length=1, max_length=120)


class GroupDetailIn(Schema):
    """Texts of the service detail page."""

    description: str | None = Field(default=None, max_length=1000)
    includes: list[str] = Field(default_factory=list, max_length=12)
    term: str | None = Field(default=None, max_length=60)
    cost: str | None = Field(default=None, max_length=60)
    guarantee: str | None = Field(default=None, max_length=200)
    upsell: str | None = Field(default=None, max_length=300)
    footnote: str | None = Field(default=None, max_length=300)
    gallery: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


class ServiceAdminOut(Schema):
    id: int
    slug: str
    name: str
    category_id: int | None
    group_id: int | None
    kind: ServiceKind
    short_description: str
    description: str | None
    items: list[str]
    price_from: int | None
    duration_minutes: int | None
    duration_days: int | None
    duration_label: str | None
    badge: str | None
    note: str | None
    online_booking: bool
    client_selects_staff: bool
    requires_resource: bool
    requires_staff: bool
    show_in_price_list: bool
    image_id: int | None
    staff_ids: list[int]
    sort_order: int


class CategoryOut(Schema):
    id: int
    slug: str
    name: str
    sort_order: int


class GroupOut(Schema):
    id: int
    slug: str
    title: str
    short_title: str | None
    summary: str | None
    tagline: str | None
    features: list[str]
    price_label: str | None
    duration_label: str | None
    badge: str | None
    is_wide: bool
    is_visible: bool
    image_id: int | None
    detail: dict[str, Any]
    sort_order: int
