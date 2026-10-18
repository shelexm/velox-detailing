"""Before/after cases and reviews: lists with publish switches and order, edit panels."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import MediaAsset, PortfolioCase, Review
from app.web.panel.common import ManagerPanel, render

router = APIRouter()


async def _media(session, studio_id: int) -> dict[int, MediaAsset]:
    return {m.id: m for m in await session.scalars(select(MediaAsset).where(MediaAsset.studio_id == studio_id))}


@router.get("/admin/{studio_id}/portfolio")
async def portfolio_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
    new: Annotated[bool, Query()] = False,
) -> Response:
    cases = list(
        await session.scalars(
            select(PortfolioCase)
            .where(PortfolioCase.studio_id == panel.studio.id)
            .order_by(PortfolioCase.sort_order, PortfolioCase.id)
        )
    )
    return render(
        request,
        "panel/portfolio.html",
        panel,
        active="portfolio",
        cases=cases,
        selected=next((c for c in cases if c.id == open_id), None),
        creating=new,
        media=await _media(session, panel.studio.id),
    )


@router.get("/admin/{studio_id}/reviews")
async def reviews_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
    new: Annotated[bool, Query()] = False,
) -> Response:
    reviews = list(
        await session.scalars(
            select(Review).where(Review.studio_id == panel.studio.id).order_by(Review.sort_order, Review.id)
        )
    )
    return render(
        request,
        "panel/reviews.html",
        panel,
        active="reviews",
        reviews=reviews,
        selected=next((r for r in reviews if r.id == open_id), None),
        creating=new,
    )
