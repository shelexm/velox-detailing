"""Telegram Mini App: the calendar page.

The page reads free times from the public API. The bot opens it from a keyboard button, so the choice
(service and start time) goes back to the chat with Telegram.WebApp.sendData: Telegram delivers it as a
message from that user, and the bot holds the slot and asks for the name and phone. Keyboard-button
Mini Apps get no initData, so the page itself never writes anything.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.api.deps import DbSession
from app.services import queries
from app.web.templating import build_templates

router = APIRouter()
templates = build_templates()


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
