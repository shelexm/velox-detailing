"""Telegram Mini App: the calendar page and the hold that needs a Telegram signature."""

from __future__ import annotations

import json
import time

import httpx
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram import sign_init_data
from app.models import Booking, Service, Studio
from app.models.enums import BookingStatus
from tests.api.conftest import first_free_slot

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


async def test_hold_needs_a_valid_signature(
    client: httpx.AsyncClient, app: FastAPI, session: AsyncSession, studio: Studio
) -> None:
    polish = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    start = await first_free_slot(client, "velox", polish)
    url = "/api/v1/tg/studios/velox/hold"
    body = {"init_data": init_data(), "service_id": polish, "starts_at": start}
    assert (await client.post(url, json=body)).status_code == 503  # no bot token configured

    original = app.state.settings
    app.state.settings = original.model_copy(update={"telegram_bot_token": SecretStr(TOKEN)})
    try:
        forged = await client.post(url, json={**body, "init_data": init_data(token="999:OTHER")})
        assert forged.status_code == 401
        held = await client.post(url, json=body)
        assert held.status_code == 201, held.text
        hold = await session.scalar(select(Booking).where(Booking.id == held.json()["hold_id"]))
        assert hold.status == BookingStatus.HOLD and hold.hold_owner == "tg:5001"
        # One active hold per Telegram user: holding again releases the previous one.
        again = await client.post(url, json=body)
        assert again.status_code == 201
        await session.refresh(hold)
        assert hold.status == BookingStatus.CANCELLED
    finally:
        app.state.settings = original
