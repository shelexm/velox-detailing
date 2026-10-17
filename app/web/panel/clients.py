"""Clients: search, segments, the client card with visit history, notes and tags."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.services import queries
from app.web.panel.common import ManagerPanel, render

router = APIRouter()

PAGE = 50
Segment = Literal["all", "regular", "new", "lapsed"]
SEGMENT_LABELS = {"all": "Все", "regular": "Постоянные", "new": "Новые", "lapsed": "Давно не были"}


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


@router.get("/admin/{studio_id}/clients")
async def clients_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    segment: Annotated[Segment, Query()] = "all",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
    new: Annotated[bool, Query()] = False,
) -> Response:
    listing = await queries.list_clients(
        session, panel.studio.id, query=q, segment=segment, limit=PAGE, offset=(page - 1) * PAGE
    )
    detail = None
    if open_id:
        try:
            detail = await queries.client_detail(session, panel.studio.id, open_id)
        except NotFoundError:
            detail = None
    return render(
        request,
        "panel/clients.html",
        panel,
        active="clients",
        listing=listing,
        q=q or "",
        segment=segment,
        segment_labels=SEGMENT_LABELS,
        page=page,
        pages=max(1, -(-listing.total // PAGE)),
        detail=detail,
        creating=new,
        initials=initials,
        now=datetime.now(UTC),
        today=panel.now().date(),
    )
