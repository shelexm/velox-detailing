"""Telegram Mini App: the calendar page and the hold it creates for the signed-in Telegram user.

The page reads free times from the public API. Holding a time needs proof of who the user is: the
initData string signed by Telegram, checked with the bot token on the server. The hold is then handed
back to the chat (Telegram.WebApp.sendData), where the bot asks for the name and phone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DbSession, PublicStudio
from app.core.errors import AppError, NotFoundError, UnauthorizedError
from app.core.telegram import InvalidInitData, hold_owner, verify_init_data
from app.models import Service
from app.schemas.common import Schema
from app.services import booking as booking_service
from app.services import queries
from app.web.templating import build_templates

router = APIRouter()
templates = build_templates()


class BotUnavailableError(AppError):
    status_code = 503
    code = "bot_unavailable"
    message = "Запись через Telegram сейчас недоступна"


class HoldIn(Schema):
    init_data: str = Field(min_length=10, max_length=4096)
    service_id: int = Field(ge=1)
    starts_at: datetime


@router.get("/tg/app", include_in_schema=False)
async def mini_app(
    request: Request, session: DbSession, service: Annotated[int | None, Query(ge=1)] = None
) -> HTMLResponse:
    from app.web.site import current_studio

    studio = await current_studio(request, session)
    services = await queries.public_services(session, studio.id)
    chosen = next((s for s in services if s.id == service), None) or (services[0] if services else None)
    return templates.TemplateResponse(
        request,
        "tg/app.html",
        {"studio": studio, "services": services, "chosen": chosen, "horizon": studio.horizon_days},
    )


@router.post("/api/v1/tg/studios/{slug}/hold", status_code=201)
async def hold(payload: HoldIn, studio: PublicStudio, session: DbSession, request: Request) -> dict:
    token = request.app.state.settings.telegram_bot_token
    if token is None:
        raise BotUnavailableError()
    try:
        user = verify_init_data(payload.init_data, token.get_secret_value())
    except InvalidInitData as exc:
        raise UnauthorizedError("Откройте календарь из чата с ботом") from exc
    service = await session.scalar(
        select(Service.id).where(Service.studio_id == studio.id, Service.id == payload.service_id)
    )
    if service is None:
        raise NotFoundError("Услуга не найдена")
    created = await booking_service.create_hold(
        session,
        studio.id,
        service_id=payload.service_id,
        starts_at=queries.ensure_aware(payload.starts_at, ZoneInfo(studio.timezone)),
        owner=hold_owner(user.id),
    )
    return {"hold_id": created.id, "starts_at": created.starts_at.isoformat(), "hold_minutes": studio.hold_minutes}
