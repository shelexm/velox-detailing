"""Panel input for site content: landing blocks, before/after cases, reviews, gift certificates."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from app.core.text import with_https
from app.schemas.common import Schema


def _clean(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    return value


def _text(value: object) -> object:
    # Keeps line breaks of longer texts, trims each line.
    if isinstance(value, str):
        lines = [" ".join(line.split()) for line in value.strip().splitlines()]
        return "\n".join(lines) or None
    return value


class SectionIn(Schema):
    content: dict[str, Any] | None = None
    is_visible: bool | None = None


class KeysIn(Schema):
    keys: list[str] = Field(min_length=1, max_length=30)


class CaseFields(Schema):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    short_title: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=400)
    car: str | None = Field(default=None, max_length=120)
    works: str | None = Field(default=None, max_length=200)
    term: str | None = Field(default=None, max_length=60)
    before_label: str | None = Field(default=None, max_length=30)
    after_label: str | None = Field(default=None, max_length=30)
    before_image_id: int | None = None
    after_image_id: int | None = None
    is_example: bool | None = None
    is_published: bool | None = None

    _c = field_validator("title", "short_title", "car", "works", "term", "before_label", "after_label", mode="before")(
        _clean
    )
    _t = field_validator("description", mode="before")(_text)


class CaseCreateIn(CaseFields):
    title: str = Field(min_length=1, max_length=120)


class ReviewFields(Schema):
    author_name: str | None = Field(default=None, max_length=120)
    car: str | None = Field(default=None, max_length=120)
    service_label: str | None = Field(default=None, max_length=80)
    text: str | None = Field(default=None, min_length=1, max_length=1500)
    rating: int | None = Field(default=None, ge=1, le=5)
    source_url: str | None = Field(default=None, max_length=500, pattern=r"^https://[^\s<>\"']+$")
    is_demo: bool | None = None
    is_published: bool | None = None

    _c = field_validator("author_name", "car", "service_label", mode="before")(_clean)
    _u = field_validator("source_url", mode="before")(with_https)
    _t = field_validator("text", mode="before")(_text)


class ReviewCreateIn(ReviewFields):
    text: str = Field(min_length=1, max_length=1500)


class GiftFields(Schema):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    value_text: str | None = Field(default=None, min_length=1, max_length=80)
    subtitle: str | None = Field(default=None, max_length=160)
    is_visible: bool | None = None

    _c = field_validator("label", "value_text", "subtitle", mode="before")(_clean)


class GiftCreateIn(GiftFields):
    label: str = Field(min_length=1, max_length=60)
    value_text: str = Field(min_length=1, max_length=80)
