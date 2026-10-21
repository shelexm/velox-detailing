"""Slots and capacity: slot step, boxes, buffers and limits, masters' online booking, client preview."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.models import Resource, Service, StudioHours
from app.schemas.common import MAX_DAY, MIN_DAY
from app.services import queries
from app.web.panel import fmt
from app.web.panel.bookings import active_staff
from app.web.panel.common import BlankAsNone, ManagerPanel, render

router = APIRouter()


@router.get("/admin/{studio_id}/slots")
async def slots_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    day: Annotated[Annotated[date, Field(ge=MIN_DAY, le=MAX_DAY)] | None, BlankAsNone, Query()] = None,
    service: Annotated[Annotated[int, Field(ge=1)] | None, BlankAsNone, Query()] = None,
) -> Response:
    studio = panel.studio
    sid = studio.id
    today = panel.now().date()
    boxes = list(
        await session.scalars(
            select(Resource)
            .where(Resource.studio_id == sid, Resource.is_active.is_(True))
            .order_by(Resource.sort_order)
        )
    )
    services = list(
        await session.scalars(
            select(Service)
            .where(Service.studio_id == sid, Service.is_active.is_(True), Service.online_booking.is_(True))
            .order_by(Service.sort_order)
        )
    )
    preview_day = day or today + timedelta(days=1)

    async def preview_for(svc: Service):
        try:
            result = await queries.availability(
                session, studio, service_id=svc.id, date_from=preview_day, days=1, staff_id=None, include_blocked=True
            )
        except NotFoundError:
            return None
        return result.days[0] if result.days else None

    chosen = next((s for s in services if s.id == service), None)
    preview = await preview_for(chosen) if chosen else None
    if chosen is None:
        # By default show a short boxed service that really has free time that day, so the grid is telling.
        boxed = [s for s in services if s.duration_minutes and s.requires_resource]
        candidates = sorted(boxed, key=lambda s: s.duration_minutes) or services
        for candidate in candidates[:6]:
            chosen, preview = candidate, await preview_for(candidate)
            if preview and any(s.available for s in preview.slots):
                break
    note = ""
    if preview and preview.slots:
        partial = next((s for s in preview.slots if 0 < s.free_places < s.total_places and not s.blocked), None)
        blocked = [s for s in preview.slots if s.blocked]
        parts = []
        if partial:
            taken = partial.total_places - partial.free_places
            parts.append(
                f"На {fmt.hm(partial.start.astimezone(panel.tz))} уже занято мест: {taken}. "
                f"Клиент видит «свободно {partial.free_places} из {partial.total_places}»."
            )
        if blocked:
            times = ", ".join(fmt.hm(b.start.astimezone(panel.tz)) for b in blocked[:6])
            parts.append(f"Старт в {times} закрыт перерывом или блокировкой и на сайте не показывается.")
        note = " ".join(parts)

    hours = list(
        await session.scalars(select(StudioHours).where(StudioHours.studio_id == sid, StudioHours.is_open.is_(True)))
    )
    day_minutes = max(
        (
            (datetime.combine(today, h.closes_at) - datetime.combine(today, h.opens_at)).total_seconds() / 60
            for h in hours
        ),
        default=0,
    )
    slots_per_day = int(day_minutes // studio.slot_step_minutes) if studio.slot_step_minutes else 0
    return render(
        request,
        "panel/slots.html",
        panel,
        active="slots",
        boxes=boxes,
        services=services,
        chosen=chosen,
        preview_day=preview_day,
        preview=preview,
        note=note,
        staff=await active_staff(session, sid),
        slots_per_day=slots_per_day,
        places_per_day=slots_per_day * len(boxes),
        today=today,
    )
