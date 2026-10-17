from __future__ import annotations

from datetime import date, time

from pydantic import Field, field_validator, model_validator

from app.core.phone import normalize_ru_phone
from app.models.enums import AbsenceKind
from app.schemas.common import Schema


def _clean(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    return value


class StaffFields(Schema):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    since_year: int | None = Field(default=None, ge=1980, le=2100)
    specializations: list[str] | None = Field(default=None, max_length=10)
    client_selectable: bool | None = None

    _names = field_validator("full_name", "short_name", "title", mode="before")(_clean)

    @field_validator("phone", mode="before")
    @classmethod
    def _phone(cls, value: object) -> object:
        value = _clean(value)
        return None if value is None else normalize_ru_phone(str(value))

    @field_validator("specializations")
    @classmethod
    def _specs(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [" ".join(v.split())[:60] for v in value if v and v.strip()]
        return list(dict.fromkeys(cleaned))


class StaffCreateIn(StaffFields):
    full_name: str = Field(min_length=1, max_length=200)


class DayHoursIn(Schema):
    weekday: int = Field(ge=0, le=6)
    is_working: bool
    starts_at: time | None = None
    ends_at: time | None = None

    @model_validator(mode="after")
    def _range(self) -> DayHoursIn:
        if self.is_working:
            if self.starts_at is None or self.ends_at is None:
                raise ValueError("Укажите начало и конец смены")
            if self.ends_at <= self.starts_at:
                raise ValueError("Конец смены позже начала")
        return self


class WeekHoursIn(Schema):
    days: list[DayHoursIn] = Field(min_length=7, max_length=7)

    @field_validator("days")
    @classmethod
    def _all_days(cls, value: list[DayHoursIn]) -> list[DayHoursIn]:
        if sorted(d.weekday for d in value) != list(range(7)):
            raise ValueError("Нужны все дни недели")
        return sorted(value, key=lambda d: d.weekday)


class IdsIn(Schema):
    ids: list[int] = Field(max_length=200)


class AbsenceIn(Schema):
    starts_on: date
    ends_on: date
    kind: AbsenceKind = AbsenceKind.VACATION
    note: str | None = Field(default=None, max_length=200)

    _note = field_validator("note", mode="before")(_clean)

    @model_validator(mode="after")
    def _order(self) -> AbsenceIn:
        if self.ends_on < self.starts_on:
            raise ValueError("Дата окончания раньше начала")
        if (self.ends_on - self.starts_on).days > 366:
            raise ValueError("Не больше года")
        return self


class StaffOut(Schema):
    id: int
    full_name: str
    short_name: str
    title: str | None
    phone: str | None
    since_year: int | None
    specializations: list[str]
    client_selectable: bool
    is_active: bool
    sort_order: int
