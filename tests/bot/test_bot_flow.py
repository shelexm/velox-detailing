"""Client dialog of the bot against the real booking services, with fake Telegram objects."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import handlers as h
from app.bot import keyboards as kb
from app.bot.context import BotContext
from app.models import Booking, Client, NotificationOutbox, Service, Studio
from app.models.enums import BookingStatus
from tests.bot.conftest import CHAT_ID, USER_ID, Contact, FakeBot, FakeCallback, FakeMessage, buttons, command


async def _press(message: FakeMessage, data: kb.CallbackData) -> FakeCallback:
    return FakeCallback(message=message)


async def book_light_polish(ctx: BotContext, state, session: AsyncSession) -> Booking:
    chat = FakeMessage()
    await h.start(FakeMessage(text="/start"), command(), state, ctx)
    await h.menu(FakeCallback(chat), kb.Menu(action="book"), state, ctx)
    assert "ШАГ 1 ИЗ 4" in chat.last
    group_button = next(b for b in buttons(chat.answers[-1][1]) if b.text.startswith("Полировка кузова"))
    group = kb.Pick.unpack(group_button.callback_data)
    await h.pick_service(FakeCallback(chat), group, state, ctx)  # two variants of polishing
    light = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    await h.pick_service(FakeCallback(chat), kb.Pick(kind="service", value=str(light)), state, ctx)
    assert "ШАГ 2 ИЗ 4" in chat.last

    await h.pick_brand(FakeCallback(chat), kb.Pick(kind="brand", value="Audi"), state)
    await h.vehicle_text(FakeMessage(text="A6, 2021", answers=chat.answers), state, ctx)
    assert "Audi A6, 2021: записали." in chat.last
    # A day at least two days ahead, so the online change and cancel deadline (24 h) has not passed.
    days = [
        kb.Pick.unpack(b.callback_data) for b in buttons(chat.answers[-1][1]) if b.callback_data.startswith("p:day")
    ]
    later = next(d for d in days if date.fromisoformat(d.value) >= date.today() + timedelta(days=2))
    await h.pick_day(FakeCallback(chat), later, state, ctx)
    slot_button = buttons(chat.answers[-1][1])[0]
    await h.pick_slot(FakeCallback(chat), kb.Pick.unpack(slot_button.callback_data), state, ctx)
    assert any("удерживается за вами" in text for text, _ in chat.answers)
    hold = await session.scalar(select(Booking).where(Booking.status == BookingStatus.HOLD))
    assert hold is not None and hold.hold_owner == f"tg:{USER_ID}"

    await h.name_text(FakeMessage(text="Алексей", answers=chat.answers), state, ctx)
    assert isinstance(chat.answers[-1][1], ReplyKeyboardMarkup)  # "Поделиться номером"
    # Someone else's contact is refused, the own one finishes the booking.
    await h.phone_contact(FakeMessage(contact=Contact("+79001112233", user_id=999), answers=chat.answers), state, ctx)
    assert "свой номер" in chat.last
    await h.phone_contact(FakeMessage(contact=Contact("79134521807"), answers=chat.answers), state, ctx)
    assert "Заявка принята" in chat.last and "Лёгкая полировка" in chat.last and "Audi A6, 2021" in chat.last
    await session.commit()  # end the read snapshot of this test session
    booking = await session.scalar(select(Booking).where(Booking.id == hold.id))
    await session.refresh(booking)
    return booking


async def test_full_booking_dialog(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    booking = await book_light_polish(ctx, state, session)
    assert booking.status == BookingStatus.NEW and booking.contact_name == "Алексей"
    client = await session.get(Client, booking.client_id)
    assert client.telegram_user_id == USER_ID and client.telegram_chat_id == CHAT_ID and client.phone == "+79134521807"
    rows = list(await session.scalars(select(NotificationOutbox).where(NotificationOutbox.booking_id == booking.id)))
    # The client got the answer in the chat; only the admins are notified.
    assert [(r.event, r.audience) for r in rows] == [("booking_created", "admins")]


async def test_my_bookings_move_and_cancel(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    booking = await book_light_polish(ctx, state, session)
    chat = FakeMessage()
    await h.mine_command(chat, ctx)
    assert "Ваши записи" in chat.last and "Лёгкая полировка" in chat.last

    await h.move_start(FakeCallback(chat), kb.Mine(action="move", booking=booking.id), ctx)
    offered = [b for b in buttons(chat.answers[-1][1]) if b.callback_data.startswith("b:day")]
    day = kb.Mine.unpack(offered[-1].callback_data)
    await h.move_day(FakeCallback(chat), day, ctx)
    slot = kb.Mine.unpack(buttons(chat.answers[-1][1])[0].callback_data)
    await h.move_slot(FakeCallback(chat), slot, ctx)
    assert "Запись перенесена" in chat.last
    await session.refresh(booking)
    assert booking.starts_at == datetime.fromtimestamp(int(slot.value), tz=UTC)

    # Another person cannot touch the booking.
    stranger = FakeCallback(chat)
    stranger.from_user = type(stranger.from_user)(id=777)
    await h.cancel_ask(stranger, kb.Mine(action="cancel", booking=booking.id), ctx)
    assert chat.last == "Запись не найдена."

    await h.cancel_ask(FakeCallback(chat), kb.Mine(action="cancel", booking=booking.id), ctx)
    assert "Отменить запись?" in chat.last
    await h.cancel_yes(FakeCallback(chat), kb.Mine(action="cancel_yes", booking=booking.id), ctx)
    assert chat.last == "Запись отменена. Будем рады видеть вас снова."
    await session.refresh(booking)
    assert booking.status == BookingStatus.CANCELLED
    events = [
        r.event
        for r in await session.scalars(select(NotificationOutbox).where(NotificationOutbox.audience == "admins"))
    ]
    assert events == ["booking_created", "booking_rescheduled", "booking_cancelled"]


async def test_cancel_deadline(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    booking = await book_light_polish(ctx, state, session)
    booking.starts_at = datetime.now(UTC) + timedelta(hours=3)
    booking.ends_at = booking.starts_at + timedelta(hours=8)
    booking.occupied_until = booking.ends_at
    await session.commit()
    chat = FakeMessage()
    await h.cancel_yes(FakeCallback(chat), kb.Mine(action="cancel_yes", booking=booking.id), ctx)
    assert "уже нельзя" in chat.last


async def test_site_booking_link_and_deep_links(
    client,
    ctx: BotContext,
    state,
    session: AsyncSession,
    studio: Studio,  # client first: it empties tables last
) -> None:
    polish = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    from tests.api.conftest import first_free_slot

    start = await first_free_slot(client, "velox", polish)
    created = await client.post(
        "/api/v1/public/studios/velox/bookings",
        json={"service_id": polish, "starts_at": start, "name": "Марина", "phone": "+79005550000", "consent": True},
    )
    token = created.json()["manage_url"].rsplit("/", 1)[-1]
    chat = FakeMessage()
    await h.start(chat, command(f"booking_{token}"), state, ctx)
    assert "уведомления о записи" in chat.answers[0][0]
    linked = await session.scalar(select(Client).where(Client.phone == "+79005550000"))
    assert linked.telegram_chat_id == CHAT_ID

    bad = FakeMessage()
    await h.start(bad, command("booking_wrongtoken"), state, ctx)
    assert "устарела" in bad.last

    deep = FakeMessage()
    await h.start(deep, command("service_ceramic"), state, ctx)  # a landing direction with one online service
    assert "ШАГ 2 ИЗ 4" in deep.last
    gift = FakeMessage()
    await h.start(gift, command("gift"), state, ctx)
    assert "сертификат" in gift.last


async def test_question_goes_to_the_admin_chat(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    chat = FakeMessage()
    await h.menu(FakeCallback(chat), kb.Menu(action="admin"), state, ctx)
    assert "не подключён" in chat.last

    db_studio = await session.get(Studio, studio.id)
    db_studio.telegram_admin_chat_id = -100777
    await session.commit()
    await h.menu(FakeCallback(chat), kb.Menu(action="admin"), state, ctx)
    bot = FakeBot()
    await h.question(FakeMessage(text="Можно керамику только на капот?", answers=chat.answers), state, bot, ctx)
    assert chat.last == "Вопрос передан администратору."
    assert bot.sent[0][0] == -100777 and f"#q{CHAT_ID}" in bot.sent[0][1] and "капот" in bot.sent[0][1]

    # The admin replies to that message in the admin chat; the answer reaches the client.
    original = FakeMessage(text=bot.sent[0][1])
    original.from_user = type(original.from_user)(id=FakeBot.id, is_bot=True)
    reply = FakeMessage(text="Да, можно", reply_to_message=original)
    reply.chat = type(reply.chat)(id=-100777, type="supergroup")
    assert await h.in_admin_chat(reply, bot, ctx)
    await h.admin_reply(reply, bot)
    assert bot.sent[-1] == (CHAT_ID, "<b>Ответ администратора</b>\nДа, можно")
    elsewhere = FakeMessage(text="x", reply_to_message=original)
    assert not await h.in_admin_chat(elsewhere, bot, ctx)  # same reply from another chat is ignored


async def test_back_buttons(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    from app.bot import texts

    def back_of(markup) -> kb.Pick:
        button = next(b for b in buttons(markup) if b.text == texts.BACK)
        return kb.Pick.unpack(button.callback_data)

    chat = FakeMessage()
    light = await session.scalar(select(Service.id).where(Service.slug == "light-polish"))
    await h.menu(FakeCallback(chat), kb.Menu(action="book"), state, ctx)
    await h.pick_service(FakeCallback(chat), kb.Pick(kind="service", value=str(light)), state, ctx)
    # Typing the model: back returns to the brand buttons.
    await h.pick_brand(FakeCallback(chat), kb.Pick(kind="brand", value="Audi"), state)
    await h.back(FakeCallback(chat), back_of(chat.answers[-1][1]), state, ctx)
    assert "ШАГ 2 ИЗ 4" in chat.last
    await h.vehicle_text(FakeMessage(text="Audi A6", answers=chat.answers), state, ctx)
    day = next(
        kb.Pick.unpack(b.callback_data) for b in buttons(chat.answers[-1][1]) if b.callback_data.startswith("p:day")
    )
    await h.pick_day(FakeCallback(chat), day, state, ctx)
    times_text = chat.last
    slot = kb.Pick.unpack(buttons(chat.answers[-1][1])[0].callback_data)
    await h.pick_slot(FakeCallback(chat), slot, state, ctx)
    # The name step goes back to the times of the same day, and no text is taken as a name meanwhile.
    await h.back(FakeCallback(chat), back_of(chat.answers[-1][1]), state, ctx)
    assert chat.last == times_text and await state.get_state() is None
    await session.commit()
    assert await session.scalar(select(Booking).where(Booking.status == BookingStatus.HOLD)) is None  # released
    await h.pick_slot(FakeCallback(chat), slot, state, ctx)
    await h.name_text(FakeMessage(text="Алексей", answers=chat.answers), state, ctx)
    # The phone step has a "« Назад" button on its reply keyboard.
    phone_keys = [k.text for row in chat.answers[-1][1].keyboard for k in row]
    assert texts.BACK in phone_keys
    await h.phone_back(FakeMessage(text=texts.BACK, answers=chat.answers), state, ctx)
    assert "ШАГ 4 ИЗ 4" in chat.last and await state.get_state() == h.Flow.name.state
    await h.name_text(FakeMessage(text="Алексей", answers=chat.answers), state, ctx)
    await h.phone_text(FakeMessage(text="+7 913 452-18-07", answers=chat.answers), state, ctx)
    assert "Заявка принята" in chat.last and texts.MENU in {b.text for b in buttons(chat.answers[-1][1])}
    # A question to the admin can be left with "« В меню", which also leaves the question mode.
    await h.menu(FakeCallback(chat), kb.Menu(action="admin"), state, ctx)
    await h.menu(FakeCallback(chat), kb.Menu(action="home"), state, ctx)
    assert await state.get_state() is None
