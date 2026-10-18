"""Schedule screen: weekly hours and breaks, special days on a month calendar, masters' shifts, time blocks."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import Resource, SpecialDay, StaffAbsence, StaffHours, StudioBreak, StudioHours, TimeBlock
from app.models.enums import SpecialDayKind
from app.web.panel import fmt
from app.web.panel.bookings import active_staff
from app.web.panel.common import ManagerPanel, render

router = APIRouter()

WEEKDAY_NAMES = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")


def _month(value: str | None, today: date) -> date:
    if value:
        try:
            year, month = (int(x) for x in value.split("-"))
            return date(year, month, 1)
        except ValueError:
            pass
    return today.replace(day=1)


@router.get("/admin/{studio_id}/schedule")
async def schedule_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    month: Annotated[str | None, Query(max_length=7)] = None,
) -> Response:
    sid = panel.studio.id
    today = panel.now().date()
    first = _month(month, today)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])

    hours = {h.weekday: h for h in await session.scalars(select(StudioHours).where(StudioHours.studio_id == sid))}
    breaks: dict[int, list[StudioBreak]] = {i: [] for i in range(7)}
    for row in await session.scalars(
        select(StudioBreak).where(StudioBreak.studio_id == sid).order_by(StudioBreak.starts_at)
    ):
        breaks[row.weekday].append(row)

    specials = list(
        await session.scalars(
            select(SpecialDay).where(SpecialDay.studio_id == sid, SpecialDay.day >= today).order_by(SpecialDay.day)
        )
    )
    month_specials = {
        s.day: s
        for s in await session.scalars(
            select(SpecialDay).where(SpecialDay.studio_id == sid, SpecialDay.day.between(first, last))
        )
    }
    staff = await active_staff(session, sid)
    absences = list(
        await session.scalars(
            select(StaffAbsence).where(
                StaffAbsence.studio_id == sid, StaffAbsence.ends_on >= first, StaffAbsence.starts_on <= last
            )
        )
    )
    vacation_days = {
        first + timedelta(days=i)
        for a in absences
        for i in range((last - first).days + 1)
        if a.starts_on <= first + timedelta(days=i) <= a.ends_on
    }
    # Month grid starting on Monday.
    grid_start = first - timedelta(days=first.weekday())
    cells = []
    day = grid_start
    while day <= last or day.weekday() != 0:
        cells.append(
            {
                "day": day,
                "in_month": day.month == first.month,
                "special": month_specials.get(day),
                "weekly_closed": not (hours.get(day.weekday()) and hours[day.weekday()].is_open),
                "vacation": day in vacation_days,
                "past": day < today,
            }
        )
        day += timedelta(days=1)

    shifts: dict[int, dict[int, StaffHours]] = {}
    for row in await session.scalars(select(StaffHours).where(StaffHours.studio_id == sid)):
        shifts.setdefault(row.staff_id, {})[row.weekday] = row
    now_absent = {a.staff_id: a for a in absences if a.ends_on >= today}

    blocks = list(
        await session.scalars(
            select(TimeBlock)
            .where(TimeBlock.studio_id == sid, TimeBlock.ends_at >= datetime.combine(today, time(0), tzinfo=panel.tz))
            .order_by(TimeBlock.starts_at)
        )
    )
    active_boxes = select(Resource).where(Resource.studio_id == sid, Resource.is_active.is_(True))
    resources = list(await session.scalars(active_boxes.order_by(Resource.sort_order)))
    return render(
        request,
        "panel/schedule.html",
        panel,
        active="schedule",
        today=today,
        weekday_names=WEEKDAY_NAMES,
        hours=[hours.get(i) for i in range(7)],
        breaks=breaks,
        specials=specials,
        month=first,
        month_title=f"{fmt.MONTHS[first.month - 1].capitalize()} {first.year}",
        prev_month=(first - timedelta(days=1)).strftime("%Y-%m"),
        next_month=(last + timedelta(days=1)).strftime("%Y-%m"),
        cells=cells,
        staff=staff,
        shifts=shifts,
        now_absent=now_absent,
        blocks=blocks,
        resources={r.id: r.name for r in resources},
        staff_names={s.id: s.short_name for s in staff},
        resource_list=resources,
        SpecialDayKind=SpecialDayKind,
    )
