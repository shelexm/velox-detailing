from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models.enums import BookingStatus
from app.services.availability import Interval
from app.web.panel.dashboard import _timeline

TZ = ZoneInfo("Europe/Moscow")
DAY = date(2026, 3, 4)


def _at(hour: int) -> datetime:
    return datetime(2026, 3, 4, hour, tzinfo=TZ)


def _booking(resource_id: int, start: int, end: int) -> SimpleNamespace:
    return SimpleNamespace(
        resource_id=resource_id,
        status=BookingStatus.CONFIRMED,
        starts_at=_at(start),
        ends_at=_at(end),
        contact_name="Марина",
        client_name=None,
        vehicle="Audi A6",
        staff_name="Андрей",
        service_name="Полировка",
        id=7,
    )


def _panel(is_manager: bool) -> SimpleNamespace:
    return SimpleNamespace(tz=TZ, is_manager=is_manager, url=lambda path: f"/admin/1{path}")


def _timeline_for(is_manager: bool) -> list[tuple[str, list]]:
    opening = Interval(_at(9), _at(18))
    _hours, rows = _timeline(_panel(is_manager), [_booking(1, 10, 12)], opening, [(1, "Бокс 1"), (2, "Бокс 2")], DAY)
    return rows


def test_manager_sees_free_time_in_every_box() -> None:
    rows = dict(_timeline_for(True))
    assert [s.kind for s in rows["Бокс 1"]] == ["free", "confirmed", "free"]
    assert [s.kind for s in rows["Бокс 2"]] == ["free"]


def test_master_timeline_has_only_their_jobs_never_free_time() -> None:
    # The list holds the master's own bookings only: other masters may be working in the "free" gaps.
    rows = _timeline_for(False)
    assert [name for name, _ in rows] == ["Бокс 1"]
    assert [s.kind for s in rows[0][1]] == ["confirmed"]
