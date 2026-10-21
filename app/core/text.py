"""Small text helpers: Latin slugs from Russian names, links typed by hand."""

from __future__ import annotations

import re

_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
        "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
)  # fmt: skip


def slugify(text: str, *, fallback: str = "item", max_length: int = 56) -> str:
    """Latin slug from a Russian name: Керамика дисков -> keramika-diskov."""
    value = text.lower().translate(_TRANSLIT)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value[:max_length].rstrip("-")) or fallback


def with_https(value: object) -> object:
    """A link as people type it: "yandex.ru/maps/x" and "http://x.ru" become https links, blank becomes None.

    Anything else (another scheme, spaces) is returned as is for the field's own check to reject.
    """
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return None
    if value[:7].lower() == "http://":
        return "https://" + value[7:]
    if "://" not in value and re.match(r"^[\w-]+(\.[\w-]+)+([/?#]|$)", value):
        return "https://" + value
    return value


def unique_slug(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    number = 2
    while f"{base}-{number}" in taken:
        number += 1
    return f"{base}-{number}"
