from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

# Query parameters with dates stay inside this window: 9999-12-31 plus a day overflows datetime arithmetic.
MIN_DAY = date(2000, 1, 1)
MAX_DAY = date(2100, 12, 31)


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


def initials(full_name: str) -> str:
    parts = [p for p in full_name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper()
