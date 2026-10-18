"""Owner screens: studio settings (contacts, bot, requisites) and panel access."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.phone import format_ru_phone
from app.models import MediaAsset, StudioMembership, User
from app.web.panel.bookings import active_staff
from app.web.panel.common import ROLE_LABELS, OwnerPanel, render

router = APIRouter()


@router.get("/admin/{studio_id}/settings")
async def settings_page(request: Request, panel: OwnerPanel, session: DbSession) -> Response:
    studio = panel.studio
    media = {
        m.id: m
        for m in await session.scalars(
            select(MediaAsset).where(MediaAsset.studio_id == studio.id).order_by(MediaAsset.sort_order, MediaAsset.id)
        )
    }
    return render(
        request,
        "panel/settings.html",
        panel,
        active="settings",
        s=studio,
        media=media,
        phone_display=format_ru_phone(studio.phone) if studio.phone else "",
    )


@router.get("/admin/{studio_id}/users")
async def users_page(request: Request, panel: OwnerPanel, session: DbSession) -> Response:
    rows = (
        await session.execute(
            select(StudioMembership, User)
            .join(User, User.id == StudioMembership.user_id)
            .where(StudioMembership.studio_id == panel.studio.id)
            .order_by(StudioMembership.role, User.full_name)
        )
    ).all()
    staff = await active_staff(session, panel.studio.id)
    return render(
        request,
        "panel/users.html",
        panel,
        active="users",
        members=rows,
        staff=staff,
        staff_names={m.id: m.short_name for m in staff},
        role_labels=ROLE_LABELS,
    )
