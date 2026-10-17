"""Services screen: the price list by sections, the edit panel, landing directions and sections."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import MediaAsset, Service, ServiceCategory, ServiceGroup, ServiceStaff
from app.models.enums import StaffSelection
from app.web.panel.bookings import active_staff
from app.web.panel.common import ManagerPanel, render

router = APIRouter()

Tab = Literal["services", "groups", "categories"]


def duration_parts(service: Service | None) -> tuple[int | None, str]:
    """Value and unit for the duration inputs."""
    if service is None:
        return None, "hours"
    if service.duration_days:
        return service.duration_days, "days"
    minutes = service.duration_minutes or 0
    if minutes and minutes % 60 == 0:
        return minutes // 60, "hours"
    return minutes or None, "minutes"


@router.get("/admin/{studio_id}/services")
async def services_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    tab: Annotated[Tab, Query()] = "services",
    q: Annotated[str | None, Query(max_length=100)] = None,
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
    new: Annotated[bool, Query()] = False,
) -> Response:
    sid = panel.studio.id
    services = list(
        await session.scalars(
            select(Service)
            .where(Service.studio_id == sid, Service.is_active.is_(True))
            .order_by(Service.sort_order, Service.id)
        )
    )
    categories = list(
        await session.scalars(
            select(ServiceCategory).where(ServiceCategory.studio_id == sid).order_by(ServiceCategory.sort_order)
        )
    )
    groups = list(
        await session.scalars(
            select(ServiceGroup).where(ServiceGroup.studio_id == sid).order_by(ServiceGroup.sort_order)
        )
    )
    staff = await active_staff(session, sid)
    links: dict[int, list[int]] = defaultdict(list)
    for service_id, staff_id in await session.execute(
        select(ServiceStaff.service_id, ServiceStaff.staff_id).where(ServiceStaff.studio_id == sid)
    ):
        links[service_id].append(staff_id)
    media = {m.id: m for m in await session.scalars(select(MediaAsset).where(MediaAsset.studio_id == sid))}

    shown = services
    if q:
        needle = q.strip().lower()
        shown = [s for s in services if needle in s.name.lower()]
    sections = []
    for category in categories:
        rows = [s for s in shown if s.category_id == category.id]
        if rows:
            sections.append((category.name, rows))
    rest = [s for s in shown if s.category_id is None or s.category_id not in {c.id for c in categories}]
    if rest:
        sections.append(("Без раздела: пакеты и осмотры", rest))

    selected = next((s for s in services if s.id == open_id), None) if tab == "services" else None
    group = next((g for g in groups if g.id == open_id), None) if tab == "groups" else None
    group_services = defaultdict(list)
    for s in services:
        if s.group_id:
            group_services[s.group_id].append(s)
    return render(
        request,
        "panel/services.html",
        panel,
        active="services",
        tab=tab,
        q=q or "",
        sections=sections,
        total=len(services),
        online_total=sum(1 for s in services if s.online_booking),
        categories=categories,
        groups=groups,
        group_services=group_services,
        staff=staff,
        staff_names={m.id: m.short_name for m in staff},
        links=links,
        media=media,
        selected=selected,
        creating=new and tab == "services",
        group=group,
        creating_group=new and tab == "groups",
        duration=duration_parts(selected),
        StaffSelection=StaffSelection,
    )
