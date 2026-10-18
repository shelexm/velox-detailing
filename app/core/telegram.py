"""Telegram helpers shared by the bot and the web app: Mini App initData check, deep-link payloads.

initData is checked as described in the Telegram Mini Apps docs: HMAC-SHA256 over the sorted
"key=value" lines with a key derived from the bot token ("WebAppData"), plus a freshness limit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode

MAX_INIT_DATA_AGE = 24 * 3600


class InvalidInitData(ValueError):
    pass


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Builds a signed initData string (used by tests and local previews)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def verify_init_data(
    init_data: str, bot_token: str, *, now: float | None = None, max_age: int = MAX_INIT_DATA_AGE
) -> TelegramUser:
    if not init_data or not bot_token:
        raise InvalidInitData("empty")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise InvalidInitData("no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InvalidInitData("bad signature")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InvalidInitData("bad auth_date") from exc
    if (now or time.time()) - auth_date > max_age:
        raise InvalidInitData("expired")
    try:
        user = json.loads(pairs["user"])
        return TelegramUser(
            id=int(user["id"]),
            first_name=str(user.get("first_name", "")),
            last_name=user.get("last_name"),
            username=user.get("username"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInitData("no user") from exc


def hold_owner(telegram_user_id: int) -> str:
    """Owner key of a held slot: one active hold per Telegram user."""
    return f"tg:{telegram_user_id}"
