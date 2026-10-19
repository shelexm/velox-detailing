"""Public API used by the site's booking form (no login)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession, PublicStudio, check_same_origin, client_ip
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Staff
from app.models.enums import ActorType, BookingSource, BookingStatus
from app.schemas.booking import (
    AvailabilityOut,
    BookingCreatedOut,
    BookingCreateIn,
    BookingManageOut,
    ServicePublicOut,
    StudioPublicOut,
)
from app.schemas.common import MAX_DAY, MIN_DAY
from app.services import booking as booking_service
from app.services import queries
from app.services.calendar import booking_ics

router = APIRouter(prefix="/api/v1/public/studios/{slug}", tags=["public"])


def _limit_reads(request: Request) -> None:
    request.app.state.limiters.public_read_by_ip.check(client_ip(request))


def limit_writes(request: Request) -> None:
    """A dependency, so it counts every attempt, including ones whose body fails validation."""
    check_same_origin(request)
    request.app.state.limiters.booking_by_ip.check(client_ip(request))


async def _staff_name(session: DbSession, staff_id: int | None) -> str | None:
    if staff_id is None:
        return None
    return await session.scalar(select(Staff.short_name).where(Staff.id == staff_id))


def _manage_links(request: Request, slug: str, token: str) -> tuple[str, str]:
    base = str(request.app.state.settings.public_base_url).rstrip("/")
    return f"{base}/booking/{token}", f"{base}/api/v1/public/studios/{slug}/bookings/manage/{token}/calendar.ics"


@router.get("", response_model_exclude_none=True)
async def studio_info(studio: PublicStudio, request: Request) -> StudioPublicOut:
    _limit_reads(request)
    return StudioPublicOut.model_validate(studio)


@router.get("/services")
async def services(studio: PublicStudio, session: DbSession, request: Request) -> list[ServicePublicOut]:
    _limit_reads(request)
    return await queries.public_services(session, studio.id)


@router.get("/availability")
async def availability(
    studio: PublicStudio,
    session: DbSession,
    request: Request,
    service_id: Annotated[int, Query(ge=1)],
    date_from: Annotated[date | None, Query(ge=MIN_DAY, le=MAX_DAY)] = None,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
    staff_id: Annotated[int | None, Query(ge=1)] = None,
) -> AvailabilityOut:
    _limit_reads(request)
    service = next((s for s in await queries.public_services(session, studio.id) if s.id == service_id), None)
    if service is None:
        raise NotFoundError("Услуга не найдена")
    if staff_id is not None and staff_id not in {s.id for s in service.staff}:
        raise ValidationFailedError("Этого мастера нельзя выбрать для услуги")
    return await queries.availability(
        session, studio, service_id=service_id, date_from=date_from, days=days, staff_id=staff_id
    )


@router.post("/bookings", status_code=201, dependencies=[Depends(limit_writes)])
async def create_booking(
    payload: BookingCreateIn, studio: PublicStudio, session: DbSession, request: Request
) -> BookingCreatedOut:
    if payload.website:
        raise ValidationFailedError()
    created = await booking_service.create_booking(
        session,
        studio.id,
        booking_service.BookingInput(
            service_id=payload.service_id,
            starts_at=queries.ensure_aware(payload.starts_at, ZoneInfo(studio.timezone)),
            staff_id=payload.staff_id,
            contact_name=payload.name,
            phone=payload.phone,
            vehicle=payload.vehicle,
            comment=payload.comment,
            consent=payload.consent,
            source=BookingSource.SITE,
        ),
        booking_service.Actor(ActorType.CLIENT),
    )
    booking = created.booking
    manage_url, calendar_url = _manage_links(request, studio.slug, created.manage_token or "")
    service = next((s for s in await queries.public_services(session, studio.id) if s.id == booking.service_id), None)
    return BookingCreatedOut(
        number=booking.number,
        status=booking.status,
        service_name=booking.service_name,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        staff_name=await _staff_name(session, booking.staff_id),
        price_from=booking.price_from,
        duration_label=service.duration_label if service else None,
        manage_url=manage_url,
        calendar_url=calendar_url,
    )


def _can_cancel(studio, booking, now: datetime) -> bool:
    return booking.status in (BookingStatus.NEW, BookingStatus.CONFIRMED) and booking.starts_at - now >= timedelta(
        hours=studio.cancel_deadline_hours
    )


@router.get("/bookings/manage/{token}")
async def manage_view(token: str, studio: PublicStudio, session: DbSession, request: Request) -> BookingManageOut:
    _limit_reads(request)
    booking = await booking_service.find_by_manage_token(session, studio.id, token)
    return BookingManageOut(
        number=booking.number,
        status=booking.status,
        service_name=booking.service_name,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        staff_name=await _staff_name(session, booking.staff_id),
        price_from=booking.price_from,
        can_cancel=_can_cancel(studio, booking, datetime.now(UTC)),
        cancel_deadline_hours=studio.cancel_deadline_hours,
    )


@router.post("/bookings/manage/{token}/cancel", dependencies=[Depends(limit_writes)])
async def manage_cancel(token: str, studio: PublicStudio, session: DbSession, request: Request) -> BookingManageOut:
    booking = await booking_service.find_by_manage_token(session, studio.id, token)
    await booking_service.cancel_by_client(
        session, studio.id, booking.id, actor=booking_service.Actor(ActorType.CLIENT)
    )
    return await manage_view(token, studio, session, request)


@router.get("/bookings/manage/{token}/calendar.ics")
async def manage_calendar(token: str, studio: PublicStudio, session: DbSession, request: Request) -> Response:
    _limit_reads(request)
    booking = await booking_service.find_by_manage_token(session, studio.id, token)
    body = booking_ics(booking, studio, host=request.url.hostname or "velox")
    return Response(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="velox-{booking.number}.ics"'},
    )
