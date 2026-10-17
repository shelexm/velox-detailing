"""Masters API for the panel: profile, hours, services, absences, order, retire."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbSession, Manager
from app.models import Staff
from app.schemas.media import OrderIn
from app.schemas.staff import AbsenceIn, IdsIn, StaffCreateIn, StaffFields, StaffOut, WeekHoursIn
from app.services import catalog
from app.services import staff as staff_service

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}/staff", tags=["admin-staff"])


@router.post("", status_code=201)
async def create_staff(payload: StaffCreateIn, access: Manager, session: DbSession) -> StaffOut:
    return StaffOut.model_validate(await staff_service.create_staff(session, access.studio, payload))


@router.patch("/{staff_id}")
async def update_staff(staff_id: int, payload: StaffFields, access: Manager, session: DbSession) -> StaffOut:
    return StaffOut.model_validate(await staff_service.update_staff(session, access.studio.id, staff_id, payload))


@router.delete("/{staff_id}", status_code=204)
async def retire_staff(staff_id: int, access: Manager, session: DbSession) -> Response:
    await staff_service.retire_staff(session, access.studio.id, staff_id)
    return Response(status_code=204)


@router.put("/{staff_id}/hours", status_code=204)
async def set_hours(staff_id: int, payload: WeekHoursIn, access: Manager, session: DbSession) -> Response:
    await staff_service.set_hours(session, access.studio.id, staff_id, payload.days)
    return Response(status_code=204)


@router.put("/{staff_id}/services", status_code=204)
async def set_services(staff_id: int, payload: IdsIn, access: Manager, session: DbSession) -> Response:
    await staff_service.set_services(session, access.studio.id, staff_id, payload.ids)
    return Response(status_code=204)


@router.post("/{staff_id}/absences", status_code=201)
async def add_absence(staff_id: int, payload: AbsenceIn, access: Manager, session: DbSession) -> dict:
    absence, clashes = await staff_service.add_absence(session, access.studio, staff_id, payload)
    return {"id": absence.id, "bookings_inside": clashes}


@router.delete("/{staff_id}/absences/{absence_id}", status_code=204)
async def delete_absence(staff_id: int, absence_id: int, access: Manager, session: DbSession) -> Response:
    await staff_service.delete_absence(session, access.studio.id, staff_id, absence_id)
    return Response(status_code=204)


@router.post("/order", status_code=204)
async def order_staff(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, Staff, access.studio.id, payload.ids)
    return Response(status_code=204)
