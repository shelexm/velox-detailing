from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.availability import (
    Hours,
    Interval,
    Rules,
    ServiceSpec,
    StudioSnapshot,
    assign,
    day_slots,
    free_places,
    grid_starts,
    nearest_available,
    on_grid,
    service_end,
)

MSK = ZoneInfo("Europe/Moscow")
MONDAY = date(2026, 10, 19)
WEDNESDAY = date(2026, 10, 21)
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=MSK)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=MSK)


def snapshot(**overrides) -> StudioSnapshot:
    rules = Rules(
        timezone=MSK,
        slot_step=timedelta(hours=1),
        buffer=timedelta(minutes=15),
        min_lead=timedelta(hours=2),
        horizon_days=30,
        respect_staff_availability=overrides.pop("respect", True),
    )
    weekday_hours = {wd: Hours(time(9), time(21)) for wd in range(6)} | {6: Hours(time(10), time(18))}
    snap = StudioSnapshot(
        rules=rules,
        weekly_hours=weekday_hours,
        breaks={wd: [(time(13), time(13, 30))] for wd in range(5)},
        resource_ids=[1, 2],
        staff_hours={
            10: {wd: Hours(time(9), time(18)) for wd in range(5)} | {5: Hours(time(10), time(16)), 6: None},
            11: {0: None} | {wd: Hours(time(10), time(19)) for wd in range(1, 7)},
        },
    )
    for key, value in overrides.items():
        setattr(snap, key, value)
    return snap


HOURS_3 = ServiceSpec(1, 180, None, True, True, (10, 11))
HOURS_8 = ServiceSpec(2, 480, None, True, True, (10, 11))
DAYS_3 = ServiceSpec(3, None, 3, True, True, (10,))
INSPECTION = ServiceSpec(4, 30, None, False, True, (10, 11))


def test_grid_starts_follow_the_slot_step() -> None:
    starts = grid_starts(snapshot(), WEDNESDAY)
    assert starts[0] == at(WEDNESDAY, 9)
    assert starts[-1] == at(WEDNESDAY, 20)
    assert len(starts) == 12


def test_same_day_service_must_end_before_closing() -> None:
    snap = snapshot()
    assert service_end(snap, HOURS_8, at(WEDNESDAY, 13)) == at(WEDNESDAY, 21)
    assert service_end(snap, HOURS_8, at(WEDNESDAY, 14)) is None


def test_break_forbids_starts_but_work_may_span_it() -> None:
    snap = snapshot(rules=Rules(MSK, timedelta(minutes=30), timedelta(0), timedelta(0), 30))
    assert assign(snap, HOURS_3, at(WEDNESDAY, 13), now=NOW) is None
    assert assign(snap, HOURS_3, at(WEDNESDAY, 12), now=NOW) is not None


def test_special_days_close_or_shorten_the_day() -> None:
    snap = snapshot(special_days={WEDNESDAY: None, date(2026, 10, 22): Hours(time(9), time(17))})
    assert grid_starts(snap, WEDNESDAY) == []
    assert grid_starts(snap, date(2026, 10, 22))[-1] == at(date(2026, 10, 22), 16)


def test_buffer_keeps_box_and_master_busy_after_the_job() -> None:
    busy = [Interval(at(WEDNESDAY, 10), at(WEDNESDAY, 13, 15))]
    snap = snapshot(resource_busy={1: busy, 2: busy})
    assert assign(snap, HOURS_3, at(WEDNESDAY, 13), now=NOW) is None
    assert assign(snap, HOURS_3, at(WEDNESDAY, 14), now=NOW) is not None


def test_capacity_counts_free_boxes() -> None:
    snap = snapshot(resource_busy={1: [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 21))]})
    start = at(WEDNESDAY, 11)
    assert free_places(snap, HOURS_3, start, start + timedelta(hours=3)) == 1
    assignment = assign(snap, HOURS_3, start, now=NOW)
    assert assignment is not None and assignment.resource_id == 2

    snap.resource_busy[2] = [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 21))]
    assert assign(snap, HOURS_3, start, now=NOW) is None


def test_requested_master_must_be_free_working_and_eligible() -> None:
    snap = snapshot(staff_busy={10: [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 12))]})
    assert assign(snap, HOURS_3, at(WEDNESDAY, 10), now=NOW, staff_id=10) is None
    assert assign(snap, HOURS_3, at(WEDNESDAY, 10), now=NOW).staff_id == 11
    assert assign(snap, HOURS_3, at(WEDNESDAY, 10), now=NOW, staff_id=99) is None
    # Master 11 does not work on Mondays.
    assert assign(snap, HOURS_3, at(date(2026, 10, 26), 10), now=NOW, staff_id=11) is None
    # Master 10 works until 18:00, an 8-hour job from 11:00 does not fit his shift.
    assert assign(snap, HOURS_8, at(WEDNESDAY, 11), now=NOW, staff_id=10) is None


def test_absence_and_master_block() -> None:
    snap = snapshot(
        staff_absences={10: [(WEDNESDAY, WEDNESDAY)]},
        staff_blocks={11: [Interval(at(WEDNESDAY, 15), at(WEDNESDAY, 16))]},
    )
    assert assign(snap, HOURS_3, at(WEDNESDAY, 10), now=NOW, staff_id=10) is None
    assert assign(snap, HOURS_3, at(WEDNESDAY, 14), now=NOW, staff_id=11) is None
    assert assign(snap, HOURS_3, at(WEDNESDAY, 16), now=NOW, staff_id=11) is not None


def test_master_availability_can_be_ignored_by_studio_rules() -> None:
    snap = snapshot(
        respect=False,
        staff_busy={
            10: [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 21))],
            11: [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 21))],
        },
    )
    assignment = assign(snap, HOURS_3, at(WEDNESDAY, 11), now=NOW)
    assert assignment is not None and assignment.staff_id is None


def test_min_lead_and_horizon() -> None:
    snap = snapshot()
    assert assign(snap, HOURS_3, at(MONDAY, 10), now=NOW) is None  # only one hour ahead
    assert assign(snap, HOURS_3, at(MONDAY, 11), now=NOW) is not None
    far = MONDAY + timedelta(days=31)
    assert assign(snap, HOURS_3, at(far, 11), now=NOW) is None
    assert assign(snap, HOURS_3, at(far, 11), now=NOW, enforce_window=False) is not None


def test_multi_day_service_ends_at_closing_of_last_working_day() -> None:
    snap = snapshot()
    assert service_end(snap, DAYS_3, at(WEDNESDAY, 12)) == at(date(2026, 10, 23), 21)
    assert service_end(snap, DAYS_3, at(WEDNESDAY, 18)) is None  # too late to use the first day
    closed_friday = snapshot(special_days={date(2026, 10, 23): None})
    assert service_end(closed_friday, DAYS_3, at(WEDNESDAY, 12)) == at(date(2026, 10, 24), 21)


def test_multi_day_service_needs_master_present_every_day() -> None:
    snap = snapshot(staff_absences={10: [(date(2026, 10, 22), date(2026, 10, 22))]})
    assert assign(snap, DAYS_3, at(WEDNESDAY, 12), now=NOW) is None


def test_studio_block_hides_starts_and_stops_same_day_overlap_only() -> None:
    block = Interval(at(WEDNESDAY, 15), at(WEDNESDAY, 17))
    snap = snapshot(studio_blocks=[block])
    assert assign(snap, HOURS_3, at(WEDNESDAY, 15), now=NOW) is None
    assert assign(snap, HOURS_3, at(WEDNESDAY, 13, 30), now=NOW, enforce_window=False) is None
    assert assign(snap, DAYS_3, at(WEDNESDAY, 12), now=NOW) is not None
    visible = [s.start for s in day_slots(snap, HOURS_3, WEDNESDAY, now=NOW)]
    assert at(WEDNESDAY, 15) not in visible and at(WEDNESDAY, 16) not in visible
    admin_view = day_slots(snap, HOURS_3, WEDNESDAY, now=NOW, include_blocked=True)
    assert any(s.blocked for s in admin_view)


def test_service_without_box_is_limited_by_masters_only() -> None:
    full = [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 21))]
    snap = snapshot(resource_busy={1: full, 2: full})
    assignment = assign(snap, INSPECTION, at(WEDNESDAY, 11), now=NOW)
    assert assignment is not None and assignment.resource_id is None


def test_day_slots_report_places() -> None:
    snap = snapshot(resource_busy={1: [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 12))]})
    slots = {s.start.hour: s for s in day_slots(snap, HOURS_3, WEDNESDAY, now=NOW)}
    assert slots[10].free_places == 1 and slots[10].total_places == 2 and slots[10].available
    assert 13 not in slots  # break


def test_nearest_available_suggests_next_free_starts() -> None:
    busy = [Interval(at(WEDNESDAY, 9), at(WEDNESDAY, 15))]
    snap = snapshot(resource_busy={1: busy, 2: busy})
    assert nearest_available(snap, HOURS_3, at(WEDNESDAY, 10), now=NOW, limit=2) == [
        at(WEDNESDAY, 15),
        at(WEDNESDAY, 16),
    ]


@pytest.mark.parametrize(
    ("moment", "expected"),
    [(at(WEDNESDAY, 10), True), (at(WEDNESDAY, 10, 30), False), (at(WEDNESDAY, 22), False)],
)
def test_on_grid(moment: datetime, expected: bool) -> None:
    assert on_grid(snapshot(), moment) is expected
