"""Site content API: landing blocks (validated by app/content/sections.py), before/after, reviews, gifts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, Manager
from app.content.sections import FIXED_SECTIONS, SECTION_MODELS, default_content, validate_section
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import GiftOption, MediaAsset, PortfolioCase, Review, SiteSection
from app.schemas.content import (
    CaseCreateIn,
    CaseFields,
    GiftCreateIn,
    GiftFields,
    KeysIn,
    ReviewCreateIn,
    ReviewFields,
    SectionIn,
)
from app.schemas.media import OrderIn
from app.services import catalog
from app.services.media import section_image_ids

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}", tags=["admin-content"])


async def _check_images(session: AsyncSession, studio_id: int, ids: set[int], field: str = "content") -> None:
    if not ids:
        return
    found = set(
        await session.scalars(select(MediaAsset.id).where(MediaAsset.studio_id == studio_id, MediaAsset.id.in_(ids)))
    )
    if found != ids:
        raise ValidationFailedError(details=[{"field": field, "message": "Изображение не найдено в медиатеке"}])


def _pydantic_details(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"].removeprefix("Value error, ")}
        for err in exc.errors()
    ]


# ----- landing blocks -----


@router.patch("/sections/{key}")
async def update_section(key: str, payload: SectionIn, access: Manager, session: DbSession) -> dict[str, Any]:
    if key not in SECTION_MODELS:
        raise NotFoundError("Блок не найден")
    sid = access.studio.id
    row = await session.scalar(select(SiteSection).where(SiteSection.studio_id == sid, SiteSection.key == key))
    if row is None:
        last = await session.scalar(select(func.max(SiteSection.sort_order)).where(SiteSection.studio_id == sid))
        row = SiteSection(
            studio_id=sid, key=key, is_visible=True, sort_order=(last or 0) + 1, content=default_content(key)
        )
        session.add(row)
    if payload.content is not None:
        try:
            content = validate_section(key, payload.content)
        except ValidationError as exc:
            raise ValidationFailedError(details=_pydantic_details(exc)) from exc
        await _check_images(session, sid, section_image_ids(content))
        row.content = content
    if payload.is_visible is not None:
        if key in FIXED_SECTIONS and not payload.is_visible:
            raise ValidationFailedError("Этот блок нельзя скрыть")
        row.is_visible = payload.is_visible
    await session.commit()
    return {"key": row.key, "is_visible": row.is_visible, "content": row.content}


@router.post("/sections/{key}/reset")
async def reset_section(key: str, access: Manager, session: DbSession) -> dict[str, Any]:
    """Back to the texts of the design mockups (images stay as they are)."""
    if key not in SECTION_MODELS:
        raise NotFoundError("Блок не найден")
    row = await session.scalar(
        select(SiteSection).where(SiteSection.studio_id == access.studio.id, SiteSection.key == key)
    )
    if row is None:
        raise NotFoundError("Блок не найден")
    fresh = default_content(key)
    for field, value in (row.content or {}).items():
        if field.endswith("image_id"):
            fresh[field] = value
    row.content = fresh
    await session.commit()
    return {"key": row.key, "content": row.content}


@router.post("/sections/order", status_code=204)
async def order_sections(payload: KeysIn, access: Manager, session: DbSession) -> Response:
    rows = {
        r.key: r for r in await session.scalars(select(SiteSection).where(SiteSection.studio_id == access.studio.id))
    }
    movable = [k for k in payload.keys if k in rows and k not in FIXED_SECTIONS]
    for position, key in enumerate(movable):
        rows[key].sort_order = position + 1
    await session.commit()
    return Response(status_code=204)


# ----- generic helpers for the three lists -----


async def _get(session: AsyncSession, model, studio_id: int, object_id: int, label: str):
    row = await session.scalar(select(model).where(model.studio_id == studio_id, model.id == object_id))
    if row is None:
        raise NotFoundError(f"{label} не найдено")
    return row


async def _new(session: AsyncSession, model, studio_id: int, values: dict[str, Any]):
    last = await session.scalar(select(func.max(model.sort_order)).where(model.studio_id == studio_id))
    row = model(studio_id=studio_id, sort_order=(last or 0) + 1, **values)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _apply(row, values: dict[str, Any], required: tuple[str, ...]) -> None:
    for field, value in values.items():
        if value is None and field in required:
            continue
        setattr(row, field, value)


def _out(row) -> dict[str, Any]:
    return {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key not in ("studio_id",)}


CASE_REQUIRED = ("title", "before_label", "after_label", "is_example", "is_published")
REVIEW_REQUIRED = ("text", "is_demo", "is_published")
GIFT_REQUIRED = ("label", "value_text", "is_visible")


# ----- before / after -----


@router.post("/portfolio", status_code=201)
async def create_case(payload: CaseCreateIn, access: Manager, session: DbSession) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    await _check_images(session, access.studio.id, {v for k, v in values.items() if k.endswith("image_id") and v})
    values.setdefault("before_label", "ДО")
    values.setdefault("after_label", "ПОСЛЕ")
    values = {k: v for k, v in values.items() if v is not None or k not in CASE_REQUIRED}
    return _out(await _new(session, PortfolioCase, access.studio.id, values))


@router.patch("/portfolio/{case_id}")
async def update_case(case_id: int, payload: CaseFields, access: Manager, session: DbSession) -> dict[str, Any]:
    row = await _get(session, PortfolioCase, access.studio.id, case_id, "Пример")
    values = payload.model_dump(exclude_unset=True)
    await _check_images(session, access.studio.id, {v for k, v in values.items() if k.endswith("image_id") and v})
    _apply(row, values, CASE_REQUIRED)
    await session.commit()
    await session.refresh(row)  # updated_at is set by the database
    return _out(row)


@router.delete("/portfolio/{case_id}", status_code=204)
async def delete_case(case_id: int, access: Manager, session: DbSession) -> Response:
    await session.delete(await _get(session, PortfolioCase, access.studio.id, case_id, "Пример"))
    await session.commit()
    return Response(status_code=204)


@router.post("/portfolio/order", status_code=204)
async def order_cases(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, PortfolioCase, access.studio.id, payload.ids)
    return Response(status_code=204)


# ----- reviews -----


@router.post("/reviews", status_code=201)
async def create_review(payload: ReviewCreateIn, access: Manager, session: DbSession) -> dict[str, Any]:
    values = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k not in REVIEW_REQUIRED
    }
    return _out(await _new(session, Review, access.studio.id, values))


@router.patch("/reviews/{review_id}")
async def update_review(review_id: int, payload: ReviewFields, access: Manager, session: DbSession) -> dict[str, Any]:
    row = await _get(session, Review, access.studio.id, review_id, "Отзыв")
    _apply(row, payload.model_dump(exclude_unset=True), REVIEW_REQUIRED)
    await session.commit()
    await session.refresh(row)  # updated_at is set by the database
    return _out(row)


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(review_id: int, access: Manager, session: DbSession) -> Response:
    await session.delete(await _get(session, Review, access.studio.id, review_id, "Отзыв"))
    await session.commit()
    return Response(status_code=204)


@router.post("/reviews/order", status_code=204)
async def order_reviews(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, Review, access.studio.id, payload.ids)
    return Response(status_code=204)


# ----- gift certificates -----


@router.post("/gifts", status_code=201)
async def create_gift(payload: GiftCreateIn, access: Manager, session: DbSession) -> dict[str, Any]:
    values = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k not in GIFT_REQUIRED
    }
    return _out(await _new(session, GiftOption, access.studio.id, values))


@router.patch("/gifts/{gift_id}")
async def update_gift(gift_id: int, payload: GiftFields, access: Manager, session: DbSession) -> dict[str, Any]:
    row = await _get(session, GiftOption, access.studio.id, gift_id, "Номинал")
    _apply(row, payload.model_dump(exclude_unset=True), GIFT_REQUIRED)
    await session.commit()
    await session.refresh(row)  # updated_at is set by the database
    return _out(row)


@router.delete("/gifts/{gift_id}", status_code=204)
async def delete_gift(gift_id: int, access: Manager, session: DbSession) -> Response:
    await session.delete(await _get(session, GiftOption, access.studio.id, gift_id, "Номинал"))
    await session.commit()
    return Response(status_code=204)


@router.post("/gifts/order", status_code=204)
async def order_gifts(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, GiftOption, access.studio.id, payload.ids)
    return Response(status_code=204)
