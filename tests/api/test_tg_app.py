"""Telegram Mini App: the calendar page and its security policy."""

from __future__ import annotations

import json
import time

import httpx

from app.core.telegram import sign_init_data
from app.models import Studio

TOKEN = "123456:TEST-TOKEN"


def init_data(user_id: int = 5001, token: str = TOKEN) -> str:
    user = json.dumps({"id": user_id, "first_name": "Алексей"})
    return sign_init_data({"auth_date": str(int(time.time())), "user": user}, token)


async def test_calendar_page(client: httpx.AsyncClient, studio: Studio) -> None:
    page = await client.get("/tg/app", headers={"Accept": "text/html"})
    assert page.status_code == 200 and "data-tg-app" in page.text
    # The script finds the day grid by this hook; service options carry data-days of their own.
    assert page.text.count("data-day-grid") == 1
    csp = page.headers["content-security-policy"]
    assert "frame-ancestors https://web.telegram.org" in csp and "https://telegram.org" in csp
    # Other pages keep the strict policy.
    assert (
        "telegram.org"
        not in (await client.get("/", headers={"Accept": "text/html"})).headers["content-security-policy"]
    )
