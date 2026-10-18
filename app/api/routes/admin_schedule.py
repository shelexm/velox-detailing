"""Schedule API for the panel: weekly hours and breaks, special days, time blocks."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbSession, Manager
from app.schemas.schedule import SpecialDayIn, StudioWeekIn, TimeBlockIn
from app.services import schedule

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}/schedule", tags=["admin-schedule"])


@router.put("/hours")
async def set_hours(payload: StudioWeekIn, access: Manager, session: DbSession) -> dict:
    outside = await schedule.set_week(session, access.studio.id, payload.days)
    return {"staff_shifts_outside": outside}


@router.post("/special-days", status_code=201)
async def save_special_day(payload: SpecialDayIn, access: Manager, session: DbSession) -> dict:
    row = await schedule.save_special_day(session, access.studio.id, payload)
    return {"id": row.id}


@router.delete("/special-days/{special_id}", status_code=204)
async def delete_special_day(special_id: int, access: Manager, session: DbSession) -> Response:
    await schedule.delete_special_day(session, access.studio.id, special_id)
    return Response(status_code=204)


@router.post("/blocks", status_code=201)
async def add_block(payload: TimeBlockIn, access: Manager, session: DbSession) -> dict:
    block, clashes = await schedule.add_block(session, access.studio, payload)
    return {"id": block.id, "bookings_inside": clashes}


@router.delete("/blocks/{block_id}", status_code=204)
async def delete_block(block_id: int, access: Manager, session: DbSession) -> Response:
    await schedule.delete_block(session, access.studio.id, block_id)
    return Response(status_code=204)
