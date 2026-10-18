"""Masters screen: cards with today's status and week load, the profile with services, hours, absences."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import Service, ServiceStaff, Staff, StaffHours
from app.models.enums import AbsenceKind, BookingStatus
from app.services import queries, stats
from app.services import staff as staff_service
from app.web.panel.common import ManagerPanel, render

router = APIRouter()

ABSENCE_LABELS = {AbsenceKind.VACATION: "Отпуск", AbsenceKind.SICK: "Больничный", AbsenceKind.DAY_OFF: "Выходной"}


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _hours_label(minutes: float) -> str:
    hours = round(minutes / 60)
    return f"{hours} ч в неделю"


@router.get("/admin/{studio_id}/staff")
async def staff_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    open_id: Annotated[int | None, Query(alias="open", ge=1)] = None,
    new: Annotated[bool, Query()] = False,
) -> Response:
    sid = panel.studio.id
    now = panel.now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    masters = list(
        await session.scalars(
            select(Staff).where(Staff.studio_id == sid, Staff.is_active.is_(True)).order_by(Staff.sort_order, Staff.id)
        )
    )
    week = await stats.staff_week(session, panel.studio, week_start)
    today_index = (today - week_start).days

    def week_percent(staff_id: int) -> int:
        days = [d for d in week.get(staff_id, []) if d.working]
        if not days:
            return 0
        total = sum((d.window.end - d.window.start).total_seconds() for d in days)
        busy = sum(d.percent / 100 * (d.window.end - d.window.start).total_seconds() for d in days)
        return round(100 * busy / total) if total else 0

    selected = None if new else next((m for m in masters if m.id == open_id), masters[0] if masters else None)
    detail = {}
    if selected:
        hours = {
            h.weekday: h
            for h in await session.scalars(
                select(StaffHours).where(StaffHours.studio_id == sid, StaffHours.staff_id == selected.id)
            )
        }
        weekly_minutes = sum(
            (datetime.combine(today, h.ends_at) - datetime.combine(today, h.starts_at)).total_seconds() / 60
            for h in hours.values()
            if h.is_working
        )
        services = list(
            await session.scalars(
                select(Service)
                .where(Service.studio_id == sid, Service.is_active.is_(True))
                .order_by(Service.sort_order, Service.id)
            )
        )
        linked = set(
            await session.scalars(
                select(ServiceStaff.service_id).where(
                    ServiceStaff.studio_id == sid, ServiceStaff.staff_id == selected.id
                )
            )
        )
        upcoming = await queries.list_bookings(
            session,
            sid,
            date_from=now,
            date_to=datetime.combine(today + timedelta(days=21), time(0), tzinfo=panel.tz),
            statuses=[BookingStatus.NEW, BookingStatus.CONFIRMED],
            staff_id=selected.id,
            limit=6,
        )
        detail = {
            "hours": [hours.get(i) for i in range(7)],
            "weekly_hours": _hours_label(weekly_minutes),
            "services": services,
            "linked": linked,
            "absences": await staff_service.absences(session, sid, selected.id, today),
            "days": week.get(selected.id, []),
            "upcoming": upcoming,
        }
    return render(
        request,
        "panel/staff.html",
        panel,
        active="staff",
        masters=masters,
        selected=selected,
        explicit=open_id is not None,
        creating=new,
        detail=detail,
        week=week,
        today=today,
        today_index=today_index,
        week_percent=week_percent,
        initials=initials,
        absence_labels=ABSENCE_LABELS,
        AbsenceKind=AbsenceKind,
        working_today=sum(1 for m in masters if m.id in week and week[m.id][today_index].working),
    )
