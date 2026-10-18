import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Booking, BookingEvent, Client, NotificationOutbox, Service, Staff, Studio
from app.models.enums import ActorType, BookingSource, BookingStatus
from app.seed.run import seed_all
from app.services import booking as svc
from app.services.booking import (
    Actor,
    BookingInput,
    DeadlinePassedError,
    HoldExpiredError,
    InvalidTransitionError,
    SlotUnavailableError,
    StaleBookingError,
)

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=MSK)  # Monday
WEDNESDAY = date(2026, 10, 21)
CLIENT = Actor(ActorType.CLIENT)
ADMIN = Actor(ActorType.USER, user_id=None)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=MSK)


@pytest.fixture
async def studio(session: AsyncSession) -> Studio:
    return await seed_all(session)


async def service_id(session: AsyncSession, studio: Studio, slug: str) -> int:
    return await session.scalar(select(Service.id).where(Service.studio_id == studio.id, Service.slug == slug))


async def staff_id(session: AsyncSession, studio: Studio, short_name: str) -> int:
    return await session.scalar(select(Staff.id).where(Staff.studio_id == studio.id, Staff.short_name == short_name))


def request(service: int, start: datetime, **extra) -> BookingInput:
    values = dict(
        service_id=service,
        starts_at=start,
        contact_name="Алексей",
        phone="+7 913 452-18-07",
        source=BookingSource.SITE,
        consent=True,
        vehicle="Audi A6, 2021",
    )
    values.update(extra)
    return BookingInput(**values)


async def test_site_booking_creates_client_history_and_outbox(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    created = await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=NOW)
    booking = created.booking
    assert booking.number == 1001
    assert booking.status == BookingStatus.NEW
    assert booking.ends_at == at(date(2026, 10, 23), 21)  # 3 working days, ends at Friday closing
    assert booking.resource_id is not None and booking.staff_id is not None
    assert created.manage_token and booking.manage_token_hash == svc.hash_token(created.manage_token)

    client = await session.get(Client, booking.client_id)
    assert client.phone == "+79134521807" and client.consent_at == NOW
    events = (await session.scalars(select(BookingEvent.kind).where(BookingEvent.booking_id == booking.id))).all()
    assert events == ["created"]
    audiences = (await session.scalars(select(NotificationOutbox.audience))).all()
    assert audiences == ["admins"]  # the client has no Telegram chat yet


async def test_same_master_cannot_be_booked_twice(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=NOW)
    with pytest.raises(SlotUnavailableError) as error:
        await svc.create_booking(
            session, studio.id, request(ceramic, at(WEDNESDAY, 13), phone="+79130000001"), CLIENT, now=NOW
        )
    assert error.value.details["alternatives"]  # the client is offered the nearest free times


async def test_two_boxes_allow_two_cars_then_slot_is_full(session: AsyncSession, studio: Studio) -> None:
    light = await service_id(session, studio, "light-polish")
    start = at(WEDNESDAY, 10)
    first = await svc.create_booking(session, studio.id, request(light, start, phone="+79130000001"), CLIENT, now=NOW)
    second = await svc.create_booking(session, studio.id, request(light, start, phone="+79130000002"), CLIENT, now=NOW)
    assert first.booking.resource_id != second.booking.resource_id
    assert first.booking.staff_id != second.booking.staff_id
    with pytest.raises(SlotUnavailableError):
        await svc.create_booking(session, studio.id, request(light, start, phone="+79130000003"), CLIENT, now=NOW)


async def test_parallel_requests_for_one_slot_never_double_book(
    sessionmaker: async_sessionmaker[AsyncSession], studio: Studio
) -> None:
    async with sessionmaker() as s:
        light = await service_id(s, studio, "light-polish")

    async def attempt(index: int) -> str:
        async with sessionmaker() as s:
            try:
                await svc.create_booking(
                    s, studio.id, request(light, at(WEDNESDAY, 10), phone=f"+7913000{index:04d}"), CLIENT, now=NOW
                )
                return "ok"
            except SlotUnavailableError:
                return "taken"

    results = await asyncio.gather(*(attempt(i) for i in range(8)))
    assert results.count("ok") == 2  # two boxes, two eligible masters
    async with sessionmaker() as s:
        active = await s.scalar(select(func.count()).select_from(Booking).where(Booking.status == BookingStatus.NEW))
        numbers = (await s.scalars(select(Booking.number).order_by(Booking.number))).all()
    assert active == 2
    assert numbers == [1001, 1002]


async def test_numbers_stay_unique_when_the_studio_was_loaded_before_the_lock(
    sessionmaker: async_sessionmaker[AsyncSession], studio: Studio
) -> None:
    """The public API loads the studio before booking; the lock must re-read the number counter."""
    async with sessionmaker() as early, sessionmaker() as other:
        light = await service_id(early, studio, "light-polish")
        loaded = await early.get(Studio, studio.id)  # kept alive, as the API route keeps its studio
        first = await svc.create_booking(other, studio.id, request(light, at(WEDNESDAY, 10)), CLIENT, now=NOW)
        second = await svc.create_booking(
            early, studio.id, request(light, at(WEDNESDAY, 10), phone="+79130000009"), CLIENT, now=NOW
        )
        assert loaded.booking_seq == second.booking.number
    assert second.booking.number == first.booking.number + 1


async def test_database_rejects_overlap_even_without_service_layer(
    sessionmaker: async_sessionmaker[AsyncSession], studio: Studio
) -> None:
    async with sessionmaker() as s:
        andrey = await staff_id(s, studio, "Андрей К.")
        ceramic = await service_id(s, studio, "ceramic-coating")
        client = Client(studio_id=studio.id, full_name="Тест", phone="+79130000009", tags=[])
        s.add(client)
        await s.commit()

    def raw_booking(number: int, start: datetime) -> Booking:
        return Booking(
            studio_id=studio.id,
            number=number,
            client_id=client.id,
            service_id=ceramic,
            staff_id=andrey,
            starts_at=start,
            ends_at=start + timedelta(hours=3),
            occupied_until=start + timedelta(hours=3),
            status=BookingStatus.NEW,
            source=BookingSource.ADMIN,
            service_name="x",
        )

    async with sessionmaker() as s:
        s.add(raw_booking(1, at(WEDNESDAY, 10)))
        await s.commit()
    async with sessionmaker() as s:
        s.add(raw_booking(2, at(WEDNESDAY, 12)))
        with pytest.raises(IntegrityError) as error:
            await s.commit()
    assert svc._is_exclusion_violation(error.value)


async def test_cancelled_booking_frees_the_slot(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    first = await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=NOW)
    await svc.change_status(session, studio.id, first.booking.id, BookingStatus.CANCELLED, ADMIN, now=NOW)
    second = await svc.create_booking(
        session, studio.id, request(ceramic, at(WEDNESDAY, 12), phone="+79130000001"), CLIENT, now=NOW
    )
    assert second.booking.status == BookingStatus.NEW
    with pytest.raises(SlotUnavailableError):  # restoring the cancelled one now collides
        await svc.change_status(session, studio.id, first.booking.id, BookingStatus.NEW, ADMIN, now=NOW)


async def test_input_validation(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    with pytest.raises(ValidationFailedError) as error:
        await svc.create_booking(
            session,
            studio.id,
            request(ceramic, at(WEDNESDAY, 12), phone="+7 913 45", contact_name=" ", consent=False),
            CLIENT,
            now=NOW,
        )
    fields = {item["field"] for item in error.value.details}
    assert fields == {"phone", "contact_name", "consent"}


async def test_online_rules(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    full_film = await service_id(session, studio, "ppf-full")
    interior = await service_id(session, studio, "interior-cleaning")
    elena = await staff_id(session, studio, "Елена О.")
    with pytest.raises(SlotUnavailableError):  # off the slot grid
        await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12, 20)), CLIENT, now=NOW)
    with pytest.raises(ValidationFailedError):  # "only after inspection"
        await svc.create_booking(session, studio.id, request(full_film, at(WEDNESDAY, 12)), CLIENT, now=NOW)
    with pytest.raises(ValidationFailedError):  # the studio assigns masters for this service
        await svc.create_booking(
            session, studio.id, request(interior, at(WEDNESDAY, 10), staff_id=elena), CLIENT, now=NOW
        )
    # The studio itself can book off-grid and services closed for online booking.
    created = await svc.create_booking(
        session,
        studio.id,
        request(full_film, at(WEDNESDAY, 9, 40), source=BookingSource.ADMIN, status=BookingStatus.CONFIRMED),
        ADMIN,
        now=NOW,
    )
    assert created.booking.status == BookingStatus.CONFIRMED and created.manage_token is None


async def test_bot_hold_blocks_slot_until_completed_or_expired(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    hold = await svc.create_hold(
        session, studio.id, service_id=ceramic, starts_at=at(WEDNESDAY, 12), owner="tg:1", now=NOW
    )
    assert hold.status == BookingStatus.HOLD
    with pytest.raises(SlotUnavailableError):
        await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=NOW)

    later = NOW + timedelta(minutes=11)
    taken = await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=later)
    assert taken.booking.status == BookingStatus.NEW
    with pytest.raises(HoldExpiredError):
        await svc.complete_hold(
            session,
            studio.id,
            hold.id,
            owner="tg:1",
            data=request(ceramic, at(WEDNESDAY, 12), source=BookingSource.TELEGRAM),
            now=later,
        )


async def test_bot_hold_completion(session: AsyncSession, studio: Studio) -> None:
    ceramic = await service_id(session, studio, "ceramic-coating")
    hold = await svc.create_hold(
        session, studio.id, service_id=ceramic, starts_at=at(WEDNESDAY, 12), owner="tg:7", now=NOW
    )
    done = await svc.complete_hold(
        session,
        studio.id,
        hold.id,
        owner="tg:7",
        data=request(ceramic, at(WEDNESDAY, 12), source=BookingSource.TELEGRAM, telegram_user_id=7, telegram_chat_id=7),
        now=NOW + timedelta(minutes=3),
    )
    assert done.booking.status == BookingStatus.NEW and done.booking.client_id is not None
    audiences = sorted((await session.scalars(select(NotificationOutbox.audience))).all())
    assert audiences == ["admins"]  # the client gets the answer right in the bot chat, no second message
    with pytest.raises(NotFoundError):  # someone else's hold
        await svc.complete_hold(session, studio.id, hold.id, owner="tg:8", data=request(ceramic, NOW), now=NOW)


async def test_client_reschedule_and_cancel_deadlines(session: AsyncSession, studio: Studio) -> None:
    light = await service_id(session, studio, "light-polish")
    created = await svc.create_booking(session, studio.id, request(light, at(WEDNESDAY, 10)), CLIENT, now=NOW)
    await svc.change_status(session, studio.id, created.booking.id, BookingStatus.CONFIRMED, ADMIN, now=NOW)

    moved = await svc.reschedule(
        session, studio.id, created.booking.id, starts_at=at(date(2026, 10, 22), 10), actor=CLIENT, now=NOW
    )
    assert moved.starts_at == at(date(2026, 10, 22), 10)
    assert moved.status == BookingStatus.NEW  # the studio confirms the new time again

    too_late = at(date(2026, 10, 21), 12)
    with pytest.raises(DeadlinePassedError):
        await svc.cancel_by_client(session, studio.id, created.booking.id, actor=CLIENT, now=too_late)
    cancelled = await svc.cancel_by_client(session, studio.id, created.booking.id, actor=CLIENT, now=NOW)
    assert cancelled.status == BookingStatus.CANCELLED


async def test_status_rules_and_stale_versions(session: AsyncSession, studio: Studio) -> None:
    light = await service_id(session, studio, "light-polish")
    created = await svc.create_booking(session, studio.id, request(light, at(WEDNESDAY, 10)), CLIENT, now=NOW)
    booking_id, version = created.booking.id, created.booking.version
    await svc.change_status(session, studio.id, booking_id, BookingStatus.CONFIRMED, ADMIN, now=NOW)
    with pytest.raises(StaleBookingError):
        await svc.change_status(
            session, studio.id, booking_id, BookingStatus.DONE, ADMIN, expected_version=version, now=NOW
        )
    await svc.change_status(session, studio.id, booking_id, BookingStatus.DONE, ADMIN, now=NOW)
    with pytest.raises(InvalidTransitionError):
        await svc.change_status(session, studio.id, booking_id, BookingStatus.NEW, ADMIN, now=NOW)


async def test_studios_are_isolated(session: AsyncSession, studio: Studio) -> None:
    other = await seed_all(session, "other-studio")
    ceramic = await service_id(session, studio, "ceramic-coating")
    created = await svc.create_booking(session, studio.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=NOW)
    with pytest.raises(NotFoundError):
        await svc.change_status(session, other.id, created.booking.id, BookingStatus.CANCELLED, ADMIN, now=NOW)
    with pytest.raises(NotFoundError):  # a service id of studio A used with studio B
        await svc.create_booking(session, other.id, request(ceramic, at(WEDNESDAY, 12)), CLIENT, now=NOW)

    foreign_staff = await staff_id(session, other, "Андрей К.")
    booking = await session.get(Booking, created.booking.id)
    booking.staff_id = foreign_staff
    with pytest.raises(IntegrityError):  # composite foreign key (studio_id, staff_id)
        await session.commit()


async def test_seed_is_idempotent(session: AsyncSession, studio: Studio) -> None:
    before = await session.scalar(select(func.count()).select_from(Service))
    await seed_all(session)
    assert await session.scalar(select(func.count()).select_from(Service)) == before == 16
