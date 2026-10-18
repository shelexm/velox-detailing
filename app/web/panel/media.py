"""Media library screen: every image with its credits and where it is used; upload, replace, delete."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import MediaAsset
from app.services import media as media_service
from app.web.panel.common import ManagerPanel, render

router = APIRouter()

Filter = Literal["all", "used", "unused", "examples"]


@router.get("/admin/{studio_id}/media")
async def media_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    show: Annotated[Filter, Query()] = "all",
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
) -> Response:
    assets = list(
        await session.scalars(
            select(MediaAsset)
            .where(MediaAsset.studio_id == panel.studio.id)
            .order_by(MediaAsset.sort_order.desc(), MediaAsset.id.desc())
        )
    )
    used = await media_service.usage_map(session, panel.studio.id)
    counts = {
        "all": len(assets),
        "used": sum(1 for a in assets if used.get(a.id)),
        "unused": sum(1 for a in assets if not used.get(a.id)),
        "examples": sum(1 for a in assets if a.is_example),
    }
    if show == "used":
        assets = [a for a in assets if used.get(a.id)]
    elif show == "unused":
        assets = [a for a in assets if not used.get(a.id)]
    elif show == "examples":
        assets = [a for a in assets if a.is_example]
    selected = next((a for a in assets if a.id == open_id), None)
    if selected is None and open_id:
        selected = await session.scalar(
            select(MediaAsset).where(MediaAsset.studio_id == panel.studio.id, MediaAsset.id == open_id)
        )
    return render(
        request,
        "panel/media.html",
        panel,
        active="media",
        assets=assets,
        used=used,
        counts=counts,
        show=show,
        selected=selected,
        thumb=lambda a: media_service.fallback_src(a, 480),
        large=lambda a: media_service.fallback_src(a, 1600),
        max_mb=media_service.MAX_UPLOAD_BYTES // (1024 * 1024),
    )
