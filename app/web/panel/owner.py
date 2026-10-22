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

# Offered in the settings; a studio keeps any other valid zone it already has (see settings_page).
TIMEZONES = (
    ("Europe/Kaliningrad", "Калининград (UTC+2)"),
    ("Europe/Moscow", "Москва, Санкт-Петербург (UTC+3)"),
    ("Europe/Samara", "Самара (UTC+4)"),
    ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
    ("Asia/Omsk", "Омск (UTC+6)"),
    ("Asia/Novosibirsk", "Новосибирск, Красноярск (UTC+7)"),
    ("Asia/Irkutsk", "Иркутск (UTC+8)"),
    ("Asia/Yakutsk", "Якутск (UTC+9)"),
    ("Asia/Vladivostok", "Владивосток (UTC+10)"),
    ("Asia/Magadan", "Магадан (UTC+11)"),
    ("Asia/Kamchatka", "Камчатка (UTC+12)"),
    ("Europe/Minsk", "Минск (UTC+3)"),
    ("Europe/Kyiv", "Киев (UTC+2/+3)"),
    ("Asia/Almaty", "Алма-Ата (UTC+5)"),
    ("Asia/Tashkent", "Ташкент (UTC+5)"),
    ("Asia/Tbilisi", "Тбилиси (UTC+4)"),
    ("Asia/Yerevan", "Ереван (UTC+4)"),
    ("Asia/Baku", "Баку (UTC+4)"),
    ("Asia/Dubai", "Дубай (UTC+4)"),
    ("Europe/Istanbul", "Стамбул (UTC+3)"),
    ("Europe/Berlin", "Берлин (UTC+1/+2)"),
    ("UTC", "UTC"),
)


@router.get("/admin/{studio_id}/settings")
async def settings_page(request: Request, panel: OwnerPanel, session: DbSession) -> Response:
    studio = panel.studio
    media = {
        m.id: m
        for m in await session.scalars(
            select(MediaAsset).where(MediaAsset.studio_id == studio.id).order_by(MediaAsset.sort_order, MediaAsset.id)
        )
    }
    timezones = list(TIMEZONES)
    if studio.timezone not in dict(timezones):
        timezones.append((studio.timezone, studio.timezone))
    return render(
        request,
        "panel/settings.html",
        panel,
        active="settings",
        s=studio,
        timezones=timezones,
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
