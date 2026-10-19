"""Starting data for a new studio. A studio that already exists is left exactly as its owner has it."""

from __future__ import annotations

import logging
from datetime import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Resource,
    Service,
    ServiceCategory,
    ServiceGroup,
    ServiceStaff,
    SiteSection,
    Staff,
    StaffHours,
    Studio,
    StudioBreak,
    StudioHours,
)
from app.models.enums import ServiceKind, StaffSelection
from app.seed import catalog_data as data

logger = logging.getLogger(__name__)


async def seed_studio(session: AsyncSession, slug: str = data.STUDIO["slug"]) -> Studio:
    studio = await session.scalar(select(Studio).where(Studio.slug == slug))
    if studio is not None:
        return studio
    studio = Studio(**{**data.STUDIO, "slug": slug})
    session.add(studio)
    await session.flush()
    for weekday, (opens, closes) in data.STUDIO_HOURS.items():
        session.add(StudioHours(studio_id=studio.id, weekday=weekday, is_open=True, opens_at=opens, closes_at=closes))
    for weekday, breaks in data.STUDIO_BREAKS.items():
        for starts, ends in breaks:
            session.add(StudioBreak(studio_id=studio.id, weekday=weekday, starts_at=starts, ends_at=ends))
    logger.info("seed: created studio %s", slug)
    return studio


async def seed_catalog(session: AsyncSession, studio: Studio) -> None:
    sid = studio.id
    if await session.scalar(select(Resource.id).where(Resource.studio_id == sid).limit(1)) is None:
        for order, name in enumerate(data.RESOURCES):
            session.add(Resource(studio_id=sid, name=name, sort_order=order, is_active=True))

    staff_ids: dict[str, int] = {}
    existing_staff = {s.full_name: s for s in await session.scalars(select(Staff).where(Staff.studio_id == sid))}
    for order, (key, item) in enumerate(data.STAFF.items()):
        staff = existing_staff.get(item["full_name"])
        if staff is None:
            staff = Staff(
                studio_id=sid,
                full_name=item["full_name"],
                short_name=item["short_name"],
                title=item["title"],
                specializations=item["specializations"],
                client_selectable=item["client_selectable"],
                is_active=True,
                sort_order=order,
            )
            session.add(staff)
            await session.flush()
            for weekday, hours in enumerate(item["hours"]):
                start, end = hours or (9, 18)
                session.add(
                    StaffHours(
                        studio_id=sid,
                        staff_id=staff.id,
                        weekday=weekday,
                        is_working=hours is not None,
                        starts_at=time(start),
                        ends_at=time(end),
                    )
                )
        staff_ids[key] = staff.id

    categories = {
        c.slug: c for c in await session.scalars(select(ServiceCategory).where(ServiceCategory.studio_id == sid))
    }
    for order, (slug, name) in enumerate(data.CATEGORIES):
        if slug not in categories:
            categories[slug] = ServiceCategory(studio_id=sid, slug=slug, name=name, sort_order=order)
            session.add(categories[slug])
    await session.flush()

    groups = {g.slug: g for g in await session.scalars(select(ServiceGroup).where(ServiceGroup.studio_id == sid))}
    for order, item in enumerate(data.GROUPS):
        if item["slug"] not in groups:
            groups[item["slug"]] = ServiceGroup(
                studio_id=sid,
                slug=item["slug"],
                title=item["title"],
                summary=item["summary"],
                features=item["features"],
                price_label=item["price_label"],
                duration_label=item["duration_label"],
                badge=item.get("badge"),
                is_wide=item.get("is_wide", False),
                detail=item["detail"],
                is_visible=True,
                sort_order=order,
            )
            session.add(groups[item["slug"]])
    for slug, group in groups.items():
        # Filled once (also for studios seeded before the field existed); edits in the panel stay.
        if group.short_title is None and slug in data.GROUP_SHORT_TITLES:
            group.short_title = data.GROUP_SHORT_TITLES[slug]
    await session.flush()

    existing = set(await session.scalars(select(Service.slug).where(Service.studio_id == sid)))
    for order, item in enumerate(data.SERVICES):
        if item["slug"] in existing:
            continue
        service = Service(
            studio_id=sid,
            slug=item["slug"],
            kind=ServiceKind(item.get("kind", "service")),
            category_id=categories[item["category"]].id if item["category"] else None,
            group_id=groups[item["group"]].id if item["group"] else None,
            name=item["name"],
            short_description=item["short"],
            items=item.get("items", []),
            price_from=item["price"],
            duration_minutes=item.get("minutes"),
            duration_days=item.get("days"),
            duration_label=item["label"],
            badge=item.get("badge"),
            note=item.get("note"),
            online_booking=item.get("online", True),
            staff_selection=StaffSelection(item.get("selection", "client")),
            requires_resource=item.get("requires_resource", True),
            requires_staff=True,
            show_in_price_list=item.get("price_list", True),
            is_active=True,
            sort_order=order,
        )
        session.add(service)
        await session.flush()
        for key in item["staff"]:
            session.add(ServiceStaff(studio_id=sid, service_id=service.id, staff_id=staff_ids[key]))
    await session.flush()


async def seed_all(session: AsyncSession, slug: str = data.STUDIO["slug"], *, media_root: Path | None = None) -> Studio:
    """Catalog always; images and site texts too when a media root is given (they need files on disk).

    Runs on every deploy (the `migrate` service), so it must not undo the owner's work: a renamed master,
    a deleted category, review or gift would come back from the design. Everything is created only for a
    studio that does not exist yet; the site content also for one that was created but never got it.
    """
    known = await session.scalar(select(Studio.id).where(Studio.slug == slug))
    studio = await seed_studio(session, slug)
    if known is not None:
        has_content = await session.scalar(select(SiteSection.studio_id).where(SiteSection.studio_id == studio.id))
        if has_content is None and media_root is not None:
            from app.seed.content import seed_content

            await seed_content(session, studio, media_root)
        return studio
    await seed_catalog(session, studio)
    await session.commit()
    if media_root is not None:
        from app.seed.content import seed_content

        await seed_content(session, studio, media_root)
    return studio
