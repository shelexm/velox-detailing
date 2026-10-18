"""Online booking rules and boxes (capacity = number of active boxes) for the "Слоты" screen."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import Field, field_validator
from sqlalchemy import func, select

from app.api.deps import DbSession, Manager
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import Booking, Resource
from app.models.enums import BookingStatus
from app.schemas.common import Schema
from app.schemas.media import OrderIn
from app.services import catalog

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}", tags=["admin-slots"])
MAX_BOXES = 20


class BookingRulesIn(Schema):
    online_booking_enabled: bool | None = None
    slot_step_minutes: int | None = None
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    min_lead_minutes: int | None = Field(default=None, ge=0, le=10080)
    horizon_days: int | None = Field(default=None, ge=1, le=365)
    cancel_deadline_hours: int | None = Field(default=None, ge=0, le=720)
    hold_minutes: int | None = Field(default=None, ge=1, le=60)
    respect_staff_availability: bool | None = None

    @field_validator("slot_step_minutes")
    @classmethod
    def _step(cls, value: int | None) -> int | None:
        if value is not None and value not in (15, 30, 60, 120):
            raise ValueError("Шаг слотов: 15, 30, 60 или 120 минут")
        return value


class ResourceIn(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("name", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return " ".join(value.split()) or None if isinstance(value, str) else value


class ResourceOut(Schema):
    id: int
    name: str
    is_active: bool
    sort_order: int


@router.patch("/booking-rules")
async def update_rules(payload: BookingRulesIn, access: Manager, session: DbSession) -> dict:
    studio = access.studio
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(studio, field, value)
    studio.updated_at = datetime.now(UTC)
    await session.commit()
    return {name: getattr(studio, name) for name in BookingRulesIn.model_fields}


@router.post("/resources", status_code=201)
async def add_box(payload: ResourceIn, access: Manager, session: DbSession) -> ResourceOut:
    sid = access.studio.id
    active = await session.scalar(select(func.count()).where(Resource.studio_id == sid, Resource.is_active.is_(True)))
    if (active or 0) >= MAX_BOXES:
        raise ValidationFailedError(f"Не больше {MAX_BOXES} мест")
    last = await session.scalar(select(func.max(Resource.sort_order)).where(Resource.studio_id == sid))
    box = Resource(
        studio_id=sid, name=payload.name or f"Бокс {(active or 0) + 1}", is_active=True, sort_order=(last or 0) + 1
    )
    session.add(box)
    await session.commit()
    return ResourceOut.model_validate(box)


async def _box(session, studio_id: int, box_id: int) -> Resource:
    box = await session.scalar(select(Resource).where(Resource.studio_id == studio_id, Resource.id == box_id))
    if box is None:
        raise NotFoundError("Бокс не найден")
    return box


@router.patch("/resources/{box_id}")
async def rename_box(box_id: int, payload: ResourceIn, access: Manager, session: DbSession) -> ResourceOut:
    box = await _box(session, access.studio.id, box_id)
    if payload.name:
        box.name = payload.name
    await session.commit()
    return ResourceOut.model_validate(box)


@router.delete("/resources/{box_id}", status_code=204)
async def remove_box(box_id: int, access: Manager, session: DbSession) -> Response:
    """Takes a box out of service. Refused while it holds upcoming bookings."""
    box = await _box(session, access.studio.id, box_id)
    pending = await session.scalar(
        select(func.count()).where(
            Booking.studio_id == access.studio.id,
            Booking.resource_id == box.id,
            Booking.status.in_((BookingStatus.HOLD, BookingStatus.NEW, BookingStatus.CONFIRMED)),
            Booking.ends_at > datetime.now(UTC),
        )
    )
    if pending:
        raise ConflictError(
            f"В «{box.name}» есть предстоящие записи ({pending}). Перенесите их, затем уберите место",
            code="box_has_bookings",
            details={"bookings": pending},
        )
    active = await session.scalar(
        select(func.count()).where(Resource.studio_id == access.studio.id, Resource.is_active.is_(True))
    )
    if box.is_active and (active or 0) <= 1:
        raise ConflictError("В студии должно остаться хотя бы одно место", code="last_box")
    box.is_active = False
    await session.commit()
    return Response(status_code=204)


@router.post("/resources/order", status_code=204)
async def order_boxes(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, Resource, access.studio.id, payload.ids)
    return Response(status_code=204)
