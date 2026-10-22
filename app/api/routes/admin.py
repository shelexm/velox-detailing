"""Studio panel API. Every route is scoped by /studios/{studio_id} and checks membership and role."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import AnyMember, DbSession, Manager, Owner
from app.core import security
from app.core.errors import ValidationFailedError
from app.models import MediaAsset
from app.models.enums import BookingStatus
from app.schemas.booking import (
    AvailabilityOut,
    BookingAdminCreateIn,
    BookingAdminOut,
    BookingDetailOut,
    BookingUpdateIn,
    ClientCreateIn,
    ClientDetailOut,
    ClientListOut,
    ClientUpdateIn,
    RescheduleIn,
    StatusChangeIn,
)
from app.schemas.common import MAX_DAY, MIN_DAY
from app.schemas.studio import StudioSettingsIn, StudioSettingsOut
from app.services import booking as booking_service
from app.services import privacy, queries
from app.services.clients import create_client, update_client

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}", tags=["admin"])

MAX_RANGE = timedelta(days=62)
# Contacts may be cleared (they disappear from the site); these settings always need a value.
REQUIRED_SETTINGS = frozenset(
    {
        "name",
        "timezone",
        "online_booking_enabled",
        "slot_step_minutes",
        "buffer_minutes",
        "min_lead_minutes",
        "horizon_days",
        "cancel_deadline_hours",
        "hold_minutes",
        "respect_staff_availability",
    }
)


def _staff_scope(access) -> int | None:
    """Masters only see their own bookings; without a linked staff record they see none."""
    if access.is_master_only:
        return access.membership.staff_id or -1
    return None


@router.get("/bookings")
async def list_bookings(
    access: AnyMember,
    session: DbSession,
    date_from: datetime,
    date_to: datetime,
    status: Annotated[list[BookingStatus] | None, Query()] = None,
    staff_id: int | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[BookingAdminOut]:
    tz = ZoneInfo(access.studio.timezone)
    start, end = queries.ensure_aware(date_from, tz), queries.ensure_aware(date_to, tz)
    if end <= start or end - start > MAX_RANGE:
        raise ValidationFailedError("Период: не больше 62 дней")
    scope = _staff_scope(access)
    return await queries.list_bookings(
        session,
        access.studio.id,
        date_from=start,
        date_to=end,
        statuses=status,
        staff_id=scope if scope is not None else staff_id,
        query=q,
    )


@router.get("/bookings/{booking_id}")
async def get_booking(access: AnyMember, session: DbSession, booking_id: int) -> BookingDetailOut:
    return await queries.booking_detail(session, access.studio.id, booking_id, staff_id=_staff_scope(access))


@router.post("/bookings", status_code=201)
async def create_booking(payload: BookingAdminCreateIn, access: Manager, session: DbSession) -> BookingDetailOut:
    created = await booking_service.create_booking(
        session,
        access.studio.id,
        booking_service.BookingInput(
            service_id=payload.service_id,
            starts_at=queries.ensure_aware(payload.starts_at, ZoneInfo(access.studio.timezone)),
            staff_id=payload.staff_id,
            contact_name=payload.contact_name,
            phone=payload.phone,
            vehicle=payload.vehicle,
            comment=payload.client_comment,
            internal_note=payload.internal_note,
            source=payload.source,
            status=payload.status,
        ),
        access.actor,
    )
    return await queries.booking_detail(session, access.studio.id, created.booking.id)


@router.patch("/bookings/{booking_id}")
async def update_booking(
    booking_id: int, payload: BookingUpdateIn, access: Manager, session: DbSession
) -> BookingDetailOut:
    await booking_service.update_details(
        session,
        access.studio.id,
        booking_id,
        access.actor,
        contact_name=payload.contact_name,
        vehicle=payload.vehicle,
        client_comment=payload.client_comment,
        internal_note=payload.internal_note,
        expected_version=payload.version,
    )
    return await queries.booking_detail(session, access.studio.id, booking_id)


@router.post("/bookings/{booking_id}/status")
async def change_status(
    booking_id: int, payload: StatusChangeIn, access: Manager, session: DbSession
) -> BookingDetailOut:
    if payload.status in (BookingStatus.HOLD, BookingStatus.EXPIRED):
        raise ValidationFailedError("Этот статус ставится автоматически")
    await booking_service.change_status(
        session,
        access.studio.id,
        booking_id,
        payload.status,
        access.actor,
        reason=payload.reason,
        expected_version=payload.version,
    )
    return await queries.booking_detail(session, access.studio.id, booking_id)


@router.post("/bookings/{booking_id}/reschedule")
async def reschedule(booking_id: int, payload: RescheduleIn, access: Manager, session: DbSession) -> BookingDetailOut:
    await booking_service.reschedule(
        session,
        access.studio.id,
        booking_id,
        starts_at=queries.ensure_aware(payload.starts_at, ZoneInfo(access.studio.timezone)),
        actor=access.actor,
        service_id=payload.service_id,
        staff_id=payload.staff_id,
        expected_version=payload.version,
    )
    return await queries.booking_detail(session, access.studio.id, booking_id)


@router.get("/availability")
async def availability(
    access: AnyMember,
    session: DbSession,
    service_id: Annotated[int, Query(ge=1)],
    date_from: Annotated[date | None, Query(ge=MIN_DAY, le=MAX_DAY)] = None,
    days: Annotated[int, Query(ge=1, le=14)] = 1,
    staff_id: int | None = None,
) -> AvailabilityOut:
    """The same calculation clients see, plus blocked times (for the "как это видит клиент" preview)."""
    return await queries.availability(
        session,
        access.studio,
        service_id=service_id,
        date_from=date_from,
        days=days,
        staff_id=staff_id,
        include_blocked=True,
    )


@router.get("/clients")
async def list_clients(
    access: Manager,
    session: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    segment: Annotated[str, Query(pattern="^(all|regular|new|lapsed)$")] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientListOut:
    return await queries.list_clients(session, access.studio.id, query=q, segment=segment, limit=limit, offset=offset)


@router.post("/clients", status_code=201)
async def add_client(payload: ClientCreateIn, access: Manager, session: DbSession) -> ClientDetailOut:
    client = await create_client(session, access.studio.id, **payload.model_dump())
    return await queries.client_detail(session, access.studio.id, client.id)


@router.get("/clients/{client_id}")
async def get_client(client_id: int, access: Manager, session: DbSession) -> ClientDetailOut:
    return await queries.client_detail(session, access.studio.id, client_id)


@router.patch("/clients/{client_id}")
async def patch_client(client_id: int, payload: ClientUpdateIn, access: Manager, session: DbSession) -> ClientDetailOut:
    await update_client(session, access.studio.id, client_id, **payload.model_dump(exclude_unset=True))
    return await queries.client_detail(session, access.studio.id, client_id)


@router.delete("/clients/{client_id}")
async def erase_client(client_id: int, access: Owner, session: DbSession) -> dict:
    """Erase the client's personal data on their request; past visits stay as anonymous rows."""
    erased = await privacy.erase_client(session, access.studio.id, client_id, access.actor)
    return {"bookings_anonymized": erased.bookings}


def _settings_out(studio) -> StudioSettingsOut:
    out = StudioSettingsOut.model_validate(studio)
    out.telegram_admin_chat_linked = studio.telegram_admin_chat_id is not None
    return out


@router.get("/settings")
async def get_settings(access: Manager) -> StudioSettingsOut:
    return _settings_out(access.studio)


@router.patch("/settings")
async def patch_settings(payload: StudioSettingsIn, access: Owner, session: DbSession) -> StudioSettingsOut:
    studio = access.studio
    if payload.logo_image_id is not None:
        owned = await session.scalar(
            select(MediaAsset.id).where(MediaAsset.studio_id == studio.id, MediaAsset.id == payload.logo_image_id)
        )
        if owned is None:
            raise ValidationFailedError(details=[{"field": "logo_image_id", "message": "Фото не найдено в медиатеке"}])
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in REQUIRED_SETTINGS and value is None:
            raise ValidationFailedError(details=[{"field": field, "message": "Поле не может быть пустым"}])
        setattr(studio, field, value)
    studio.updated_at = datetime.now(UTC)
    await session.commit()
    return _settings_out(studio)


@router.post("/telegram/link-code")
async def telegram_link_code(access: Owner, session: DbSession) -> dict:
    """One-time code for "/link CODE" in the admins' Telegram chat; valid 15 minutes, only its hash is stored."""
    code = security.new_token()[:10].upper().replace("-", "X").replace("_", "Y")
    expires = datetime.now(UTC) + timedelta(minutes=15)
    access.studio.telegram_link_code_hash = security.token_hash(code)
    access.studio.telegram_link_expires_at = expires
    await session.commit()
    return {"code": code, "command": f"/link {code}", "expires_at": expires.isoformat()}


@router.delete("/telegram/admin-chat", status_code=204)
async def telegram_unlink(access: Owner, session: DbSession) -> Response:
    access.studio.telegram_admin_chat_id = None
    access.studio.telegram_link_code_hash = None
    access.studio.telegram_link_expires_at = None
    await session.commit()
    return Response(status_code=204)


@router.get("/me")
async def my_role(access: AnyMember) -> dict:
    return {"studio_id": access.studio.id, "role": access.membership.role, "staff_id": access.membership.staff_id}
