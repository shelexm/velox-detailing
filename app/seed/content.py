"""Seed the media library and the site content (sections, portfolio, reviews, gift options).

Idempotent: existing images (by seed_key) and existing rows are left as they are, so edits made in the
panel survive repeated runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.sections import SECTION_MODELS, default_content
from app.models import GiftOption, MediaAsset, PortfolioCase, Review, ServiceGroup, SiteSection, Studio
from app.seed import media_data as data
from app.services.media import ingest_image

logger = logging.getLogger(__name__)
SEED_MEDIA_DIR = Path(__file__).resolve().parent / "media"


async def seed_media(session: AsyncSession, studio: Studio, media_root: Path) -> dict[str, int]:
    existing = {
        key: asset_id
        for key, asset_id in await session.execute(
            select(MediaAsset.seed_key, MediaAsset.id).where(
                MediaAsset.studio_id == studio.id, MediaAsset.seed_key.is_not(None)
            )
        )
    }
    for item in data.MEDIA:
        if item["key"] in existing:
            continue
        path = SEED_MEDIA_DIR / item["file"]
        asset = await ingest_image(
            session,
            studio_id=studio.id,
            media_root=media_root,
            data=path.read_bytes(),
            original_name=path.name,
            alt=item["alt"],
            provenance={
                "source_url": item["source_url"],
                "author": item["author"],
                "author_url": item["author_url"],
                "license": item["license"],
                "license_url": item["license_url"],
            },
            is_example=item["is_example"],
            seed_key=item["key"],
            max_bytes=None,
        )
        existing[item["key"]] = asset.id
        logger.info("seed: image %s", item["key"])
    await session.commit()
    return existing


async def seed_site_content(session: AsyncSession, studio: Studio, media: dict[str, int]) -> None:
    sid = studio.id

    for group in await session.scalars(select(ServiceGroup).where(ServiceGroup.studio_id == sid)):
        if group.tagline is None and group.slug in data.GROUP_TAGLINES:
            group.tagline = data.GROUP_TAGLINES[group.slug]
        if group.image_id is None and group.slug in data.GROUP_IMAGES:
            group.image_id = media.get(data.GROUP_IMAGES[group.slug])
        if "gallery" not in group.detail and group.slug in data.GROUP_GALLERIES:
            gallery = [
                {"image_id": media[key], "label": label}
                for key, label in data.GROUP_GALLERIES[group.slug]
                if key in media
            ]
            group.detail = {**group.detail, "gallery": gallery}

    present = set(await session.scalars(select(SiteSection.key).where(SiteSection.studio_id == sid)))
    for order, key in enumerate(SECTION_MODELS):
        if key in present:
            continue
        content = default_content(key)
        for (section, field), media_key in data.SECTION_IMAGES.items():
            if section == key and media_key in media:
                content[field] = media[media_key]
        if key == "materials":
            for tile, media_key in zip(content["tiles"], data.MATERIAL_TILE_IMAGES, strict=False):
                tile["image_id"] = media.get(media_key)
        session.add(SiteSection(studio_id=sid, key=key, is_visible=True, sort_order=order, content=content))

    if not await session.scalar(select(func.count()).select_from(PortfolioCase).where(PortfolioCase.studio_id == sid)):
        for order, case in enumerate(data.PORTFOLIO):
            session.add(
                PortfolioCase(
                    studio_id=sid,
                    title=case["title"],
                    short_title=case["short_title"],
                    description=case["description"],
                    works=case["works"],
                    term=case["term"],
                    before_label=case.get("before_label", "ДО"),
                    after_label=case.get("after_label", "ПОСЛЕ"),
                    before_image_id=media.get(case["before"]),
                    after_image_id=media.get(case["after"]),
                    is_example=True,
                    is_published=True,
                    sort_order=order,
                )
            )

    if not await session.scalar(select(func.count()).select_from(Review).where(Review.studio_id == sid)):
        for order, review in enumerate(data.REVIEWS):
            session.add(Review(studio_id=sid, is_demo=True, is_published=True, sort_order=order, **review))

    if not await session.scalar(select(func.count()).select_from(GiftOption).where(GiftOption.studio_id == sid)):
        for order, (label, value, subtitle) in enumerate(data.GIFTS):
            session.add(
                GiftOption(
                    studio_id=sid, label=label, value_text=value, subtitle=subtitle, is_visible=True, sort_order=order
                )
            )
    await session.commit()


async def seed_content(session: AsyncSession, studio: Studio, media_root: Path) -> None:
    media = await seed_media(session, studio, media_root)
    await seed_site_content(session, studio, media)
