"""Form descriptions for landing blocks, built from the block models in app/content/sections.py.

The panel template renders these specs, so a new field in a block model appears in the panel by itself.
"""

from __future__ import annotations

import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

LABELS = {
    "eyebrow": "Надзаголовок",
    "title": "Заголовок",
    "title_mobile": "Заголовок на телефоне",
    "title_lines": "Строки заголовка",
    "lead": "Текст под заголовком",
    "lead_mobile": "Текст на телефоне",
    "cta": "Кнопка",
    "cta_primary": "Главная кнопка",
    "cta_secondary": "Вторая кнопка",
    "cta_telegram": "Подпись про Telegram",
    "image_id": "Фото",
    "mobile_image_id": "Фото для телефона",
    "map_image_id": "Схема проезда",
    "image_caption": "Подпись к фото",
    "quality": "Пункты под кнопками",
    "label": "Метка",
    "text": "Текст",
    "prices_link": "Ссылка на цены",
    "more_label": "Кнопка «Подробнее»",
    "book_label": "Кнопка записи",
    "note": "Сноска",
    "example_label": "Метка примеров",
    "drag_hint": "Подсказка ползунка",
    "column_label": "Подпись колонки",
    "packages_title": "Заголовок пакетов",
    "choose_label": "Кнопка выбора пакета",
    "packages_note": "Сноска к пакетам",
    "features": "Пункты",
    "qr_hint": "Подпись к QR-коду",
    "items": "Пункты",
    "icon": "Значок",
    "tiles": "Плитки",
    "equipment_title": "Заголовок оборудования",
    "equipment": "Оборудование",
    "name": "Название",
    "value": "Значение",
    "steps": "Этапы",
    "duration": "Длительность",
    "demo_label": "Метка демо-отзывов",
    "all_reviews_label": "Ссылка на все отзывы: текст",
    "all_reviews_url": "Ссылка на все отзывы: адрес",
    "card_title": "Заголовок карточки",
    "validity": "Срок действия",
    "number_sample": "Пример номера",
    "tab_online": "Вкладка «Онлайн»",
    "tab_telegram": "Вкладка «Telegram»",
    "submit_label": "Кнопка отправки",
    "consent_text": "Текст согласия",
    "success_title": "Заголовок после записи",
    "success_text": "Текст после записи",
    "about": "Текст в подвале",
    "description": "Описание для поисковиков",
}
ICON_LABELS = {
    "master": "Мастер",
    "gauge": "Оборудование",
    "drop": "Капля",
    "plan": "График",
    "check": "Галочка",
    "shield": "Щит",
}


@dataclass
class FieldSpec:
    name: str
    label: str
    kind: str  # text | textarea | lines | image | url | select | list
    max_length: int | None = None
    options: list[tuple[str, str]] = field(default_factory=list)
    children: list[FieldSpec] = field(default_factory=list)
    max_items: int | None = None


def _max_length(info: FieldInfo) -> int | None:
    for meta in info.metadata:
        if getattr(meta, "max_length", None):
            return meta.max_length
    return None


def _pattern(info: FieldInfo) -> str | None:
    for meta in info.metadata:
        if getattr(meta, "pattern", None):
            return meta.pattern
    return None


def _args(annotation: Any) -> tuple[Any, ...]:
    return typing.get_args(annotation)


def _spec(name: str, info: FieldInfo) -> FieldSpec:
    label = LABELS.get(name, name.replace("_", " ").capitalize())
    annotation = info.annotation
    origin = typing.get_origin(annotation)
    if name.endswith("image_id"):
        return FieldSpec(name, label, "image")
    if origin is list:
        (item,) = _args(annotation)
        max_items = next((m.max_length for m in info.metadata if getattr(m, "max_length", None)), None)
        if isinstance(item, type) and issubclass(item, BaseModel):
            children = [_spec(n, i) for n, i in item.model_fields.items()]
            return FieldSpec(name, label, "list", children=children, max_items=max_items)
        return FieldSpec(name, label, "lines", max_items=max_items)
    pattern = _pattern(info)
    if pattern and pattern.startswith("^(") and pattern.endswith(")$"):
        values = re.findall(r"[a-z_]+", pattern)
        return FieldSpec(name, label, "select", options=[(v, ICON_LABELS.get(v, v)) for v in values])
    optional = isinstance(annotation, types.UnionType) or origin is typing.Union
    if optional and pattern and "https" in pattern:
        return FieldSpec(name, label, "url", max_length=_max_length(info))
    length = _max_length(info)
    return FieldSpec(name, label, "textarea" if length and length > 120 else "text", max_length=length)


def form_spec(model: type[BaseModel]) -> list[FieldSpec]:
    return [_spec(name, info) for name, info in model.model_fields.items()]
