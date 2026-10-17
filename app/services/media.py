"""Media library: validate uploads, keep the original privately, publish resized AVIF/WebP/JPEG variants.

Files: MEDIA_ROOT/<studio_id>/<storage_key>/original.<ext>   (never served: may contain EXIF/GPS)
       MEDIA_ROOT/<studio_id>/<storage_key>/w<width>.<format>  (served at /media/..., metadata stripped)
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import MediaAsset, PortfolioCase, Service, ServiceGroup, SiteSection

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 50_000_000
MIN_SIDE = 200
WIDTHS = (480, 960, 1600, 2400)
ALLOWED = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "AVIF": "avif"}
ENCODERS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("avif", "AVIF", {"quality": 58, "speed": 6}),
    ("webp", "WEBP", {"quality": 78, "method": 6}),
    ("jpg", "JPEG", {"quality": 82, "optimize": True, "progressive": True}),
)
VARIANT_NAME = r"^w\d{3,4}\.(avif|webp|jpg)$"

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class ProcessedImage:
    original_ext: str
    width: int
    height: int
    variants: list[tuple[str, int, int, bytes]] = field(default_factory=list)  # format, width, height, data


def process_image(data: bytes, *, max_bytes: int | None = MAX_UPLOAD_BYTES) -> ProcessedImage:
    """CPU-bound; call through asyncio.to_thread. Decoding is the validation (the extension is ignored)."""
    if max_bytes is not None and len(data) > max_bytes:
        raise ValidationFailedError(f"Файл больше {max_bytes // (1024 * 1024)} МБ")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValidationFailedError("Это не изображение или файл повреждён") from exc
    if fmt not in ALLOWED:
        raise ValidationFailedError("Поддерживаются JPG, PNG, WebP и AVIF")
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        background = Image.new("RGB", image.size, (7, 7, 8))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    image = image.convert("RGB")
    width, height = image.size
    if min(width, height) < MIN_SIDE:
        raise ValidationFailedError(f"Слишком маленькое изображение: нужно от {MIN_SIDE} px по меньшей стороне")

    result = ProcessedImage(original_ext=ALLOWED[fmt], width=width, height=height)
    targets = sorted({w for w in WIDTHS if w < width} | {min(width, WIDTHS[-1])})
    for target in targets:
        resized = image if target == width else image.resize((target, round(height * target / width)), Image.LANCZOS)
        for ext, pil_format, options in ENCODERS:
            buffer = io.BytesIO()
            # New encodes carry no EXIF/GPS: nothing from the original metadata is passed on.
            resized.save(buffer, pil_format, **options)
            result.variants.append((ext, target, resized.size[1], buffer.getvalue()))
    return result


def _write_files(directory: Path, original: bytes, processed: ProcessedImage) -> list[dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / f"original.{processed.original_ext}").write_bytes(original)
    variants = []
    for ext, width, height, data in processed.variants:
        name = f"w{width}.{ext}"
        (directory / name).write_bytes(data)
        variants.append({"format": ext, "width": width, "height": height, "file": name, "bytes": len(data)})
    return variants


async def ingest_image(
    session: AsyncSession,
    *,
    studio_id: int,
    media_root: Path,
    data: bytes,
    original_name: str | None,
    alt: str = "",
    title: str | None = None,
    provenance: dict[str, Any] | None = None,
    is_example: bool = False,
    seed_key: str | None = None,
    max_bytes: int | None = MAX_UPLOAD_BYTES,
) -> MediaAsset:
    processed = await asyncio.to_thread(process_image, data, max_bytes=max_bytes)
    storage_key = uuid.uuid4().hex
    directory = media_root / str(studio_id) / storage_key
    variants = await asyncio.to_thread(_write_files, directory, data, processed)
    order = await session.scalar(
        select(MediaAsset.sort_order).where(MediaAsset.studio_id == studio_id).order_by(MediaAsset.sort_order.desc())
    )
    asset = MediaAsset(
        studio_id=studio_id,
        storage_key=storage_key,
        original_name=(original_name or "")[:200] or None,
        mime=f"image/{'jpeg' if processed.original_ext == 'jpg' else processed.original_ext}",
        width=processed.width,
        height=processed.height,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        variants=variants,
        alt=alt[:300],
        title=title,
        is_example=is_example,
        seed_key=seed_key,
        sort_order=(order or 0) + 1,
        **(provenance or {}),
    )
    session.add(asset)
    try:
        await session.flush()
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return asset


def media_url(asset: MediaAsset, file_name: str) -> str:
    return f"/media/{asset.studio_id}/{asset.storage_key}/{file_name}"


def srcsets(asset: MediaAsset) -> dict[str, str]:
    by_format: dict[str, list[str]] = {}
    for variant in sorted(asset.variants, key=lambda v: v["width"]):
        by_format.setdefault(variant["format"], []).append(f"{media_url(asset, variant['file'])} {variant['width']}w")
    return {fmt: ", ".join(items) for fmt, items in by_format.items()}


def fallback_src(asset: MediaAsset, preferred_width: int = 1600) -> str:
    jpgs = sorted((v for v in asset.variants if v["format"] == "jpg"), key=lambda v: v["width"])
    if not jpgs:
        return ""
    chosen = next((v for v in jpgs if v["width"] >= preferred_width), jpgs[-1])
    return media_url(asset, chosen["file"])


def section_image_ids(content: Any) -> set[int]:
    """Every value under a key ending with 'image_id' anywhere in a JSON document."""
    found: set[int] = set()
    if isinstance(content, dict):
        for key, value in content.items():
            if key.endswith("image_id") and isinstance(value, int):
                found.add(value)
            else:
                found |= section_image_ids(value)
    elif isinstance(content, list):
        for item in content:
            found |= section_image_ids(item)
    return found


async def usages(session: AsyncSession, studio_id: int, asset_id: int) -> list[str]:
    """Human-readable places where an image is used (the panel shows them before deletion)."""
    places = []
    for name in await session.scalars(
        select(Service.name).where(Service.studio_id == studio_id, Service.image_id == asset_id)
    ):
        places.append(f"Услуга «{name}»")
    for group in await session.scalars(select(ServiceGroup).where(ServiceGroup.studio_id == studio_id)):
        if group.image_id == asset_id or asset_id in section_image_ids(group.detail):
            places.append(f"Направление «{group.title}»")
    for case in await session.scalars(select(PortfolioCase).where(PortfolioCase.studio_id == studio_id)):
        if asset_id in (case.before_image_id, case.after_image_id):
            places.append(f"Работа «{case.title}»")
    for section in await session.scalars(select(SiteSection).where(SiteSection.studio_id == studio_id)):
        if asset_id in section_image_ids(section.content):
            places.append(f"Блок сайта «{section.key}»")
    return places


async def delete_asset(session: AsyncSession, *, studio_id: int, asset_id: int, media_root: Path) -> None:
    asset = await session.scalar(select(MediaAsset).where(MediaAsset.studio_id == studio_id, MediaAsset.id == asset_id))
    if asset is None:
        raise NotFoundError("Изображение не найдено")
    places = await usages(session, studio_id, asset_id)
    if places:
        raise ConflictError(
            "Изображение используется на сайте. Сначала замените его в этих местах", code="media_in_use", details=places
        )
    directory = media_root / str(studio_id) / asset.storage_key
    await session.delete(asset)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, directory, True)
