"""Media library API: upload, replace the file, edit credits, order, delete (refused while used)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession, Manager
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import MediaAsset
from app.schemas.media import MediaOut, MediaUpdateIn, OrderIn
from app.services import media as media_service

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}/media", tags=["admin-media"])


async def _read_upload(file: UploadFile) -> bytes:
    # Read one byte past the limit so an oversized file is rejected without loading all of it.
    data = await file.read(media_service.MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ValidationFailedError(details=[{"field": "file", "message": "Выберите файл"}])
    if len(data) > media_service.MAX_UPLOAD_BYTES:
        limit = media_service.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationFailedError(details=[{"field": "file", "message": f"Файл больше {limit} МБ"}])
    return data


def media_out(asset: MediaAsset, usages: list[str] | None = None) -> MediaOut:
    return MediaOut(
        id=asset.id,
        thumb=media_service.fallback_src(asset, 480),
        large=media_service.fallback_src(asset, 1600),
        width=asset.width,
        height=asset.height,
        bytes=asset.bytes,
        alt=asset.alt,
        title=asset.title,
        original_name=asset.original_name,
        source_url=asset.source_url,
        author=asset.author,
        author_url=asset.author_url,
        license=asset.license,
        license_url=asset.license_url,
        is_example=asset.is_example,
        created_at=asset.created_at,
        usages=usages or [],
    )


async def _asset(session, studio_id: int, asset_id: int) -> MediaAsset:
    asset = await session.scalar(select(MediaAsset).where(MediaAsset.studio_id == studio_id, MediaAsset.id == asset_id))
    if asset is None:
        raise NotFoundError("Изображение не найдено")
    return asset


def _as_file_error(exc: ValidationFailedError) -> ValidationFailedError:
    return ValidationFailedError(details=exc.details or [{"field": "file", "message": exc.message}])


@router.get("")
async def list_media(access: Manager, session: DbSession) -> list[MediaOut]:
    rows = await session.scalars(
        select(MediaAsset)
        .where(MediaAsset.studio_id == access.studio.id)
        .order_by(MediaAsset.sort_order.desc(), MediaAsset.id.desc())
    )
    return [media_out(a) for a in rows]


@router.post("", status_code=201)
async def upload(
    request: Request,
    access: Manager,
    session: DbSession,
    file: Annotated[UploadFile, File()],
    alt: Annotated[str, Form(max_length=300)] = "",
    author: Annotated[str, Form(max_length=200)] = "",
    source_url: Annotated[str, Form(max_length=500)] = "",
    license: Annotated[str, Form(max_length=120)] = "",
    is_example: Annotated[bool, Form()] = False,
) -> MediaOut:
    data = await _read_upload(file)
    credits = MediaUpdateIn(author=author or None, source_url=source_url or None, license=license or None)
    try:
        asset = await media_service.ingest_image(
            session,
            studio_id=access.studio.id,
            media_root=request.app.state.settings.media_root,
            data=data,
            original_name=file.filename,
            alt=alt.strip(),
            provenance={k: v for k, v in credits.model_dump(include={"author", "source_url", "license"}).items() if v},
            is_example=is_example,
        )
    except ValidationFailedError as exc:
        raise _as_file_error(exc) from exc
    await session.commit()
    return media_out(asset)


@router.post("/order", status_code=204)
async def reorder(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    """The first id is shown first in the library."""
    assets = {
        a.id: a
        for a in await session.scalars(
            select(MediaAsset).where(MediaAsset.studio_id == access.studio.id, MediaAsset.id.in_(payload.ids))
        )
    }
    for position, asset_id in enumerate(payload.ids):
        if asset_id in assets:
            assets[asset_id].sort_order = len(payload.ids) - position
    await session.commit()
    return Response(status_code=204)


@router.post("/{asset_id}/file")
async def replace(
    asset_id: int, request: Request, access: Manager, session: DbSession, file: Annotated[UploadFile, File()]
) -> MediaOut:
    asset = await _asset(session, access.studio.id, asset_id)
    data = await _read_upload(file)
    try:
        asset = await media_service.replace_file(
            session, asset, media_root=request.app.state.settings.media_root, data=data, original_name=file.filename
        )
    except ValidationFailedError as exc:
        raise _as_file_error(exc) from exc
    return media_out(asset, await media_service.usages(session, access.studio.id, asset.id))


@router.get("/{asset_id}")
async def get_media(asset_id: int, access: Manager, session: DbSession) -> MediaOut:
    asset = await _asset(session, access.studio.id, asset_id)
    return media_out(asset, await media_service.usages(session, access.studio.id, asset.id))


@router.patch("/{asset_id}")
async def update_media(asset_id: int, payload: MediaUpdateIn, access: Manager, session: DbSession) -> MediaOut:
    asset = await _asset(session, access.studio.id, asset_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "alt":
            value = (value or "").strip()
        elif field == "is_example":
            value = bool(value)
        elif isinstance(value, str):
            value = value.strip() or None
        setattr(asset, field, value)
    await session.commit()
    return media_out(asset, await media_service.usages(session, access.studio.id, asset.id))


@router.delete("/{asset_id}", status_code=204)
async def delete_media(asset_id: int, request: Request, access: Manager, session: DbSession) -> Response:
    await media_service.delete_asset(
        session, studio_id=access.studio.id, asset_id=asset_id, media_root=request.app.state.settings.media_root
    )
    return Response(status_code=204)
