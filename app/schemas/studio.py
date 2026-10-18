from __future__ import annotations

import re

from pydantic import Field, field_validator

from app.core.phone import normalize_ru_phone
from app.schemas.common import Schema

_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class StudioSettingsOut(Schema):
    id: int
    slug: str
    name: str
    timezone: str
    city: str | None
    address: str | None
    address_note: str | None
    route_url: str | None
    phone: str | None
    whatsapp_url: str | None
    telegram_bot_username: str | None
    email: str | None
    schedule_text: str | None
    legal_name: str | None
    inn: str | None
    brand_name: str | None
    brand_tagline: str | None
    logo_image_id: int | None
    online_booking_enabled: bool
    slot_step_minutes: int
    buffer_minutes: int
    min_lead_minutes: int
    horizon_days: int
    cancel_deadline_hours: int
    hold_minutes: int
    respect_staff_availability: bool
    telegram_admin_chat_linked: bool = False


class StudioSettingsIn(Schema):
    """Every field is optional: only the provided ones change. An empty string clears a contact."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    address_note: str | None = Field(default=None, max_length=300)
    route_url: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=32)
    whatsapp_url: str | None = Field(default=None, max_length=300)
    telegram_bot_username: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)
    schedule_text: str | None = Field(default=None, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)
    inn: str | None = Field(default=None, max_length=12)
    brand_name: str | None = Field(default=None, max_length=24)
    brand_tagline: str | None = Field(default=None, max_length=40)
    logo_image_id: int | None = Field(default=None, ge=1)
    online_booking_enabled: bool | None = None
    slot_step_minutes: int | None = None
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    min_lead_minutes: int | None = Field(default=None, ge=0, le=10080)
    horizon_days: int | None = Field(default=None, ge=1, le=365)
    cancel_deadline_hours: int | None = Field(default=None, ge=0, le=720)
    hold_minutes: int | None = Field(default=None, ge=1, le=60)
    respect_staff_availability: bool | None = None

    @field_validator("slot_step_minutes")
    @classmethod
    def _step(cls, value: int | None) -> int | None:
        if value is not None and value not in (15, 30, 60, 120):
            raise ValueError("Шаг слотов: 15, 30, 60 или 120 минут")
        return value

    @field_validator("route_url", "whatsapp_url", mode="before")
    @classmethod
    def _url(cls, value: object) -> object:
        value = _blank_to_none(value)
        if value is not None and not re.match(r"^https://[^\s<>\"']+$", str(value)):
            raise ValueError("Ссылка должна начинаться с https://")
        return value

    @field_validator("brand_name", "brand_tagline", mode="before")
    @classmethod
    def _brand_text(cls, value: object) -> object:
        value = _blank_to_none(value)
        return None if value is None else " ".join(str(value).split())

    @field_validator("telegram_bot_username", mode="before")
    @classmethod
    def _username(cls, value: object) -> object:
        value = _blank_to_none(value)
        if value is None:
            return None
        value = str(value).strip().lstrip("@")
        if not _USERNAME.match(value):
            raise ValueError("Имя бота: латиница, цифры и _, от 5 символов")
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def _phone(cls, value: object) -> object:
        value = _blank_to_none(value)
        return None if value is None else normalize_ru_phone(str(value))

    @field_validator("inn", mode="before")
    @classmethod
    def _inn(cls, value: object) -> object:
        value = _blank_to_none(value)
        if value is not None and not re.fullmatch(r"\d{10}|\d{12}", str(value).strip()):
            raise ValueError("ИНН: 10 или 12 цифр")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value: object) -> object:
        value = _blank_to_none(value)
        if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value).strip()):
            raise ValueError("Некорректный e-mail")
        return value

    @field_validator("city", "address", "address_note", "schedule_text", "legal_name", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        return _blank_to_none(value)
