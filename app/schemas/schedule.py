from __future__ import annotations

from datetime import date, time
from itertools import pairwise
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.models.enums import SpecialDayKind
from app.schemas.common import Schema


def _clean(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    return value


class BreakIn(Schema):
    starts_at: time
    ends_at: time

    @model_validator(mode="after")
    def _order(self) -> BreakIn:
        if self.ends_at <= self.starts_at:
            raise ValueError("Конец перерыва позже начала")
        return self


class StudioDayIn(Schema):
    weekday: int = Field(ge=0, le=6)
    is_open: bool
    opens_at: time | None = None
    closes_at: time | None = None
    breaks: list[BreakIn] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _hours(self) -> StudioDayIn:
        if not self.is_open:
            return self
        if self.opens_at is None or self.closes_at is None:
            raise ValueError("Укажите время открытия и закрытия")
        if self.closes_at <= self.opens_at:
            raise ValueError("Закрытие позже открытия")
        ordered = sorted(self.breaks, key=lambda b: b.starts_at)
        for item in ordered:
            if item.starts_at < self.opens_at or item.ends_at > self.closes_at:
                raise ValueError("Перерыв должен быть внутри рабочих часов")
        for first, second in pairwise(ordered):
            if second.starts_at < first.ends_at:
                raise ValueError("Перерывы пересекаются")
        return self


class StudioWeekIn(Schema):
    days: list[StudioDayIn] = Field(min_length=7, max_length=7)

    @field_validator("days")
    @classmethod
    def _all_days(cls, value: list[StudioDayIn]) -> list[StudioDayIn]:
        if sorted(d.weekday for d in value) != list(range(7)):
            raise ValueError("Нужны все дни недели")
        return sorted(value, key=lambda d: d.weekday)


class SpecialDayIn(Schema):
    day: date
    kind: SpecialDayKind
    opens_at: time | None = None
    closes_at: time | None = None
    note: str | None = Field(default=None, max_length=200)

    _note = field_validator("note", mode="before")(_clean)

    @model_validator(mode="after")
    def _hours(self) -> SpecialDayIn:
        if self.kind == SpecialDayKind.SHORT:
            if self.opens_at is None or self.closes_at is None:
                raise ValueError("Для сокращённого дня укажите часы")
            if self.closes_at <= self.opens_at:
                raise ValueError("Закрытие позже открытия")
        else:
            self.opens_at = self.closes_at = None
        return self


class TimeBlockIn(Schema):
    day: date
    starts_at: time
    ends_at: time
    scope: Literal["studio", "resource", "staff"] = "studio"
    resource_id: int | None = None
    staff_id: int | None = None
    reason: str | None = Field(default=None, max_length=200)

    _reason = field_validator("reason", mode="before")(_clean)

    @model_validator(mode="after")
    def _check(self) -> TimeBlockIn:
        if self.ends_at <= self.starts_at:
            raise ValueError("Конец блокировки позже начала")
        if self.scope == "resource" and self.resource_id is None:
            raise ValueError("Выберите бокс")
        if self.scope == "staff" and self.staff_id is None:
            raise ValueError("Выберите мастера")
        return self
