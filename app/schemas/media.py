from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import Schema


def _https_or_none(value: object) -> object:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    value = str(value).strip()
    if not re.match(r"^https?://[^\s<>\"']+$", value):
        raise ValueError("Ссылка должна начинаться с https://")
    return value


class MediaOut(Schema):
    id: int
    thumb: str
    large: str
    width: int
    height: int
    bytes: int
    alt: str
    title: str | None
    original_name: str | None
    source_url: str | None
    author: str | None
    author_url: str | None
    license: str | None
    license_url: str | None
    is_example: bool
    created_at: datetime
    usages: list[str] = Field(default_factory=list)


class MediaUpdateIn(Schema):
    alt: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=200)
    author_url: str | None = Field(default=None, max_length=500)
    license: str | None = Field(default=None, max_length=120)
    license_url: str | None = Field(default=None, max_length=500)
    is_example: bool | None = None

    _urls = field_validator("source_url", "author_url", "license_url", mode="before")(_https_or_none)


class OrderIn(Schema):
    ids: list[int] = Field(min_length=1, max_length=500)
