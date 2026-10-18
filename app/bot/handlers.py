"""Telegram handlers. They only translate chat actions into calls of app/services and app/bot/logic."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import select

from app.bot import keyboards as kb
from app.bot import logic, texts
from app.bot.context import BotContext
from app.core import security
from app.core.errors import AppError, NotFoundError, ValidationFailedError
from app.core.phone import InvalidPhoneError, normalize_ru_phone
from app.core.telegram import hold_owner
from app.models import Booking, Client, ServiceCategory
from app.models.enums import ActorType, BookingSource, BookingStatus
from app.services import booking as booking_service
from app.services.booking import (
    Actor,
    BookingInput,
    DeadlinePassedError,
    HoldExpiredError,
    InvalidTransitionError,
    SlotUnavailableError,
)
from app.web.templating import plural

logger = logging.getLogger("app.bot")
client_router = Router(name="client")
client_router.message.filter(F.chat.type == "private")
admin_router = Router(name="admin")
QUESTION_TAG = re.compile(r"#q(\d+)")
CLIENT = Actor(ActorType.CLIENT)
STUDIO_STAFF = Actor(ActorType.USER)  # an admin acting from the studio's Telegram chat


class Flow(StatesGroup):
    vehicle = State()
    name = State()
    phone = State()
    question = State()


# ---------------------------------------------------------------- start and menu


@client_router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, ctx: BotContext) -> None:
    await state.clear()
    payload = (command.args or "").strip()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        if payload.startswith("booking_"):
            await _link_site_booking(message, session, studio, payload.removeprefix("booking_"))
            return
        if payload.startswith(("service_", "package_")):
            slug = payload.split("_", 1)[1]
            if await _start_with_slug(message, state, session, studio, slug):
                return
        if payload == "gift":
            await message.answer(
                "Подарочный сертификат оформим в студии на сумму или на услугу. Напишите администратору, "
                "на какую сумму или услугу нужен сертификат.",
                reply_markup=kb.after_cancel(),
            )
            return
        await message.answer(texts.WELCOME.format(name=texts.e(studio.name)), reply_markup=kb.main_menu())


@client_router.message(Command("book"))
async def book_command(message: Message, state: FSMContext, ctx: BotContext) -> None:
    await state.clear()
    await _service_step(message, ctx)


@client_router.message(Command("mine"))
async def mine_command(message: Message, ctx: BotContext) -> None:
    await _show_mine(message, ctx, message.from_user.id)


@client_router.callback_query(kb.Menu.filter())
async def menu(callback: CallbackQuery, callback_data: kb.Menu, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    message = callback.message
    if callback_data.action in {"book", "home"}:
        await _release_hold(state, ctx, callback.from_user.id)
    if callback_data.action == "book":
        await state.clear()
        await _service_step(message, ctx)
    elif callback_data.action == "mine":
        await _show_mine(message, ctx, callback.from_user.id)
    elif callback_data.action == "prices":
        await _show_prices(message, ctx)
    elif callback_data.action == "admin":
        await _ask_admin(message, state, ctx)
    else:
        await state.clear()
        async with ctx.session() as session:
            studio = await logic.studio_by_slug(session, ctx.studio_slug)
        await message.answer(texts.WELCOME.format(name=texts.e(studio.name)), reply_markup=kb.main_menu())


async def _show_prices(message: Message, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        services = await logic.online_services(session, studio.id)
        categories = {
            c.id: c.name
            for c in await session.scalars(select(ServiceCategory).where(ServiceCategory.studio_id == studio.id))
        }
    lines = ["<b>Услуги и цены</b>"]
    current = object()
    for service in sorted(services, key=lambda s: (s.category_id is None, s.category_id or 0, s.sort_order)):
        if service.category_id != current:
            current = service.category_id
            lines.append(f"\n<code>{texts.e(categories.get(service.category_id, 'ДРУГОЕ').upper())}</code>")
        duration, price = logic.service_summary(service)
        lines.append(f"{texts.e(service.name)}: {texts.e(price)}" + (f" · {texts.e(duration)}" if duration else ""))
    lines.append("\nЦены для седана среднего размера, точную сумму назовём после осмотра.")
    await message.answer(
        "\n".join(lines), reply_markup=kb.choices([("Записаться", kb.Menu(action="book"))], back=kb.Menu(action="home"))
    )


# ---------------------------------------------------------------- booking flow


async def _service_step(message: Message, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        if not studio.online_booking_enabled:
            await message.answer(
                "Онлайн-запись сейчас недоступна. Напишите администратору.", reply_markup=kb.after_cancel()
            )
            return
        items = await logic.service_menu(session, studio.id)
    buttons = [(i.label, kb.Pick(kind=i.kind, value=str(i.id))) for i in items]
    await message.answer(texts.STEP_SERVICE, reply_markup=kb.choices(buttons, back=kb.Menu(action="home")))


async def _start_with_slug(message: Message, state: FSMContext, session, studio, slug: str) -> bool:
    from app.models import Service, ServiceGroup

    service = await session.scalar(
        select(Service).where(Service.studio_id == studio.id, Service.slug == slug, Service.is_active.is_(True))
    )
    if service is not None and service.online_booking:
        await _vehicle_step(message, state, session, studio, service.id, message.from_user.id)
        return True
    group = await session.scalar(
        select(ServiceGroup).where(ServiceGroup.studio_id == studio.id, ServiceGroup.slug == slug)
    )
    if group is not None:
        title, members = await logic.group_variants(session, studio.id, group.id)
        if len(members) == 1:
            await _vehicle_step(message, state, session, studio, members[0].id, message.from_user.id)
            return True
        if members:
            await _variants(message, title, members)
            return True
    return False


async def _variants(message: Message, title: str, members) -> None:
    buttons = [
        (f"{s.name} · {texts.price_text(s.price_from)}", kb.Pick(kind="service", value=str(s.id))) for s in members
    ]
    await message.answer(
        texts.STEP_VARIANT.format(group=texts.e(title)),
        reply_markup=kb.choices(buttons, back=kb.Pick(kind="back", value="service")),
    )


async def _vehicle_step(message: Message, state: FSMContext, session, studio, service_id: int, user_id: int) -> None:
    await logic.get_service(session, studio.id, service_id)
    await state.set_state(Flow.vehicle)
    await state.update_data(service_id=service_id, brand=None)
    await message.answer(texts.STEP_VEHICLE, reply_markup=kb.brands())


@client_router.callback_query(kb.Pick.filter(F.kind.in_({"group", "service"})))
async def pick_service(callback: CallbackQuery, callback_data: kb.Pick, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            if callback_data.kind == "group":
                title, members = await logic.group_variants(session, studio.id, int(callback_data.value))
                await _variants(callback.message, title, members)
            else:
                await _vehicle_step(
                    callback.message, state, session, studio, int(callback_data.value), callback.from_user.id
                )
        except NotFoundError as exc:
            await callback.message.answer(exc.message, reply_markup=kb.main_menu())


@client_router.callback_query(kb.Pick.filter(F.kind == "brand"))
async def pick_brand(callback: CallbackQuery, callback_data: kb.Pick, state: FSMContext) -> None:
    await callback.answer()
    brand = None if callback_data.value == "other" else callback_data.value
    await state.update_data(brand=brand)
    await state.set_state(Flow.vehicle)
    prompt = texts.STEP_VEHICLE_MODEL.format(brand=brand) if brand else "Напишите марку и модель одним сообщением."
    await callback.message.answer(
        prompt,
        reply_markup=kb.choices([("Пропустить", kb.Pick(kind="skip"))], back=kb.Pick(kind="back", value="vehicle")),
    )


@client_router.callback_query(kb.Pick.filter(F.kind == "skip"))
async def skip_vehicle(callback: CallbackQuery, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    data = await state.get_data()
    await _day_step(callback.message, state, ctx, vehicle=data.get("brand"))


@client_router.message(Flow.vehicle, F.text)
async def vehicle_text(message: Message, state: FSMContext, ctx: BotContext) -> None:
    data = await state.get_data()
    text = " ".join(message.text.split())[:120]
    brand = data.get("brand")
    vehicle = text if not brand or text.lower().startswith(brand.lower()) else f"{brand} {text}"
    await _day_step(message, state, ctx, vehicle=vehicle)


async def _day_step(message: Message, state: FSMContext, ctx: BotContext, *, vehicle: str | None) -> None:
    data = await state.get_data()
    if not data.get("service_id"):
        await _service_step(message, ctx)
        return
    await state.update_data(vehicle=vehicle)
    await state.set_state(None)
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        service = await logic.get_service(session, studio.id, data["service_id"])
        options = await logic.free_days(session, studio, service.id)
    duration, price = logic.service_summary(service)
    if vehicle:
        text = texts.STEP_DAY.format(
            vehicle=f"{texts.e(vehicle)}: ",
            service=texts.e(service.name),
            duration=texts.e(duration),
            price=texts.e(price),
        )
    else:
        text = texts.STEP_DAY_NO_CAR.format(
            service=texts.e(service.name), duration=texts.e(duration), price=texts.e(price)
        )
    if not options:
        await message.answer(f"{text}\n\n{texts.NO_FREE_DAYS}", reply_markup=kb.after_cancel())
        return
    await message.answer(text, reply_markup=kb.days(options))
    if ctx.webapp_enabled:
        url = f"{ctx.base_url}/tg/app?service={service.id}"
        await message.answer("Или выберите дату и время в календаре:", reply_markup=kb.calendar_button(url))


@client_router.callback_query(kb.Pick.filter(F.kind == "day"))
async def pick_day(callback: CallbackQuery, callback_data: kb.Pick, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    await state.update_data(day=callback_data.value)
    await _time_step(callback.message, state, ctx)


async def _time_step(message: Message, state: FSMContext, ctx: BotContext) -> None:
    data = await state.get_data()
    await state.set_state(None)
    day = date.fromisoformat(data["day"])
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        starts = await logic.free_starts(session, studio, data["service_id"], day)
    if not starts:
        await message.answer(
            "На этот день время уже разобрали. Выберите другой день.",
            reply_markup=kb.choices([], back=kb.Pick(kind="back", value="day")),
        )
        return
    await message.answer(
        texts.STEP_TIME.format(day=texts.day_long(day)), reply_markup=kb.times(starts, logic.tz(studio))
    )


async def _release_hold(state: FSMContext, ctx: BotContext, user_id: int) -> None:
    if (await state.get_data()).get("hold_id") is None:
        return
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        await booking_service.release_holds(session, studio.id, hold_owner(user_id))
    await state.update_data(hold_id=None)


@client_router.callback_query(kb.Pick.filter(F.kind == "back"))
async def back(callback: CallbackQuery, callback_data: kb.Pick, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    await _release_hold(state, ctx, callback.from_user.id)
    data = await state.get_data()
    if callback_data.value == "vehicle" and data.get("service_id"):
        await state.set_state(Flow.vehicle)
        await callback.message.answer(texts.STEP_VEHICLE, reply_markup=kb.brands())
    elif callback_data.value == "day" and data.get("service_id"):
        await _day_step(callback.message, state, ctx, vehicle=data.get("vehicle"))
    elif callback_data.value == "time" and data.get("service_id") and data.get("day"):
        await _time_step(callback.message, state, ctx)
    else:
        await _service_step(callback.message, ctx)


@client_router.callback_query(kb.Pick.filter(F.kind == "slot"))
async def pick_slot(callback: CallbackQuery, callback_data: kb.Pick, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    data = await state.get_data()
    start = datetime.fromtimestamp(int(callback_data.value), tz=UTC)
    await _hold(callback.message, state, ctx, data["service_id"], start, callback.from_user)


@client_router.message(F.web_app_data)
async def from_calendar(message: Message, state: FSMContext, ctx: BotContext) -> None:
    """The calendar Mini App hands back the chosen service and start; Telegram vouches for the sender."""
    try:
        choice = json.loads(message.web_app_data.data)
        service_id = int(choice["service_id"])
        start = datetime.fromisoformat(choice["starts_at"])
        if start.tzinfo is None:
            raise ValueError("naive start")
    except (TypeError, ValueError, KeyError):
        await message.answer(texts.UNKNOWN, reply_markup=ReplyKeyboardRemove())
        return
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            await logic.get_service(session, studio.id, service_id)
        except AppError as exc:
            await message.answer(exc.message, reply_markup=ReplyKeyboardRemove())
            return
    # The day is kept so that "« Назад" from the name step shows the times of that day.
    await state.update_data(service_id=service_id, day=start.astimezone(logic.tz(studio)).date().isoformat())
    await _hold(message, state, ctx, service_id, start, message.from_user, remove_keyboard=True)


async def _hold(
    message: Message,
    state: FSMContext,
    ctx: BotContext,
    service_id: int,
    start: datetime,
    user,
    *,
    remove_keyboard: bool = False,
) -> None:
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            hold = await booking_service.create_hold(
                session, studio.id, service_id=service_id, starts_at=start, owner=hold_owner(user.id)
            )
        except SlotUnavailableError:
            await message.answer(texts.SLOT_TAKEN, reply_markup=kb.choices([], back=kb.Pick(kind="back", value="time")))
            return
        except AppError as exc:
            await message.answer(exc.message, reply_markup=kb.main_menu())
            return
        await state.update_data(hold_id=hold.id)
        await message.answer(
            texts.HOLD_TAKEN.format(
                when=texts.e(texts.when(hold.starts_at, logic.tz(studio))), minutes=studio.hold_minutes
            ),
            reply_markup=ReplyKeyboardRemove() if remove_keyboard else None,
        )
    await _name_step(message, state, ctx, user)


async def _name_step(message: Message, state: FSMContext, ctx: BotContext, user) -> None:
    await state.set_state(Flow.name)
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        client = await logic.client_by_telegram(session, studio.id, user.id)
    known = client.full_name if client else user.first_name
    items = [(f"Я {known}", kb.Pick(kind="name", value="known"))] if known else []
    markup = kb.choices(items, back=kb.Pick(kind="back", value="time"))
    await state.update_data(known_name=known)
    await message.answer(texts.STEP_NAME, reply_markup=markup)


@client_router.callback_query(kb.Pick.filter(F.kind == "name"))
async def pick_known_name(callback: CallbackQuery, state: FSMContext, ctx: BotContext) -> None:
    await callback.answer()
    data = await state.get_data()
    await _phone_step(callback.message, state, ctx, data.get("known_name") or callback.from_user.first_name)


@client_router.message(Flow.name, F.text)
async def name_text(message: Message, state: FSMContext, ctx: BotContext) -> None:
    name = " ".join(message.text.split())[:120]
    if not name or name.startswith("/"):
        await message.answer(texts.STEP_NAME)
        return
    await _phone_step(message, state, ctx, name)


async def _phone_step(message: Message, state: FSMContext, ctx: BotContext, name: str) -> None:
    await state.update_data(name=name)
    await state.set_state(Flow.phone)
    await message.answer(
        f"{texts.STEP_PHONE.format(name=texts.e(name))}\n\n{texts.CONSENT.format(url=ctx.base_url + '/privacy')}",
        reply_markup=kb.share_phone(),
    )


@client_router.message(Flow.phone, F.text == texts.BACK)
async def phone_back(message: Message, state: FSMContext, ctx: BotContext) -> None:
    # The hold stays: the name step goes on to the same time.
    await message.answer("Вернёмся на шаг назад.", reply_markup=ReplyKeyboardRemove())
    await _name_step(message, state, ctx, message.from_user)


@client_router.message(Flow.phone, F.contact)
async def phone_contact(message: Message, state: FSMContext, ctx: BotContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer(
            "Отправьте, пожалуйста, свой номер кнопкой ниже или напишите его.", reply_markup=kb.share_phone()
        )
        return
    await _finish(message, state, ctx, message.contact.phone_number)


@client_router.message(Flow.phone, F.text)
async def phone_text(message: Message, state: FSMContext, ctx: BotContext) -> None:
    await _finish(message, state, ctx, message.text)


async def _finish(message: Message, state: FSMContext, ctx: BotContext, raw_phone: str) -> None:
    try:
        phone = normalize_ru_phone(raw_phone)
    except InvalidPhoneError:
        await message.answer(texts.PHONE_HINT, reply_markup=kb.share_phone())
        return
    data = await state.get_data()
    user = message.from_user
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            created = await booking_service.complete_hold(
                session,
                studio.id,
                data["hold_id"],
                owner=hold_owner(user.id),
                data=BookingInput(
                    service_id=data["service_id"],
                    starts_at=datetime.now(UTC),
                    contact_name=data.get("name") or user.first_name,
                    phone=phone,
                    source=BookingSource.TELEGRAM,
                    vehicle=data.get("vehicle"),
                    consent=True,
                    telegram_user_id=user.id,
                    telegram_chat_id=message.chat.id,
                    telegram_username=user.username,
                ),
            )
        except HoldExpiredError:
            await message.answer(texts.HOLD_EXPIRED, reply_markup=ReplyKeyboardRemove())
            await _day_step(message, state, ctx, vehicle=data.get("vehicle"))
            return
        except (NotFoundError, KeyError):
            await state.clear()
            await message.answer(texts.HOLD_EXPIRED, reply_markup=ReplyKeyboardRemove())
            await _service_step(message, ctx)
            return
        except ValidationFailedError:
            await message.answer(texts.PHONE_HINT, reply_markup=kb.share_phone())
            return
        booking = created.booking
        card = await logic.booking_text(
            session,
            studio,
            booking,
            "✓ Заявка принята",
            footer="Администратор подтвердит запись в рабочее время и напишет сюда. Напомним за день до визита.",
        )
    await state.clear()
    await message.answer(f"Спасибо! Номер {texts.e(phone)} получили.", reply_markup=ReplyKeyboardRemove())
    await message.answer(card, reply_markup=kb.after_booking(booking.id, studio.route_url))


# ---------------------------------------------------------------- my bookings, move, cancel


async def _show_mine(message: Message, ctx: BotContext, user_id: int) -> None:
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        client = await logic.client_by_telegram(session, studio.id, user_id)
        if client is None:
            await message.answer(texts.NOTHING_UPCOMING, reply_markup=kb.main_menu())
            return
        upcoming, past = await logic.client_bookings(session, studio.id, client.id)
        if not upcoming and not past:
            await message.answer(texts.NOTHING_UPCOMING, reply_markup=kb.main_menu())
            return
        parts = ["<b>Ваши записи</b>"]
        if upcoming:
            parts.append(await logic.booking_text(session, studio, upcoming[0], "Ближайшая"))
            for other in upcoming[1:3]:
                parts.append(
                    f"№ {other.number}: {texts.e(other.service_name)}, "
                    f"<code>{texts.e(texts.when(other.starts_at, logic.tz(studio)))}</code>"
                )
        else:
            parts.append(texts.NOTHING_UPCOMING)
        if past:
            parts.append("\n<code>ПРОШЕДШИЕ</code>")
            parts.extend(
                f"{texts.e(b.service_name)}: {b.starts_at.astimezone(logic.tz(studio)):%d.%m.%Y}" for b in past
            )
    await message.answer(
        "\n\n".join(parts[:2]) + ("\n" + "\n".join(parts[2:]) if len(parts) > 2 else ""),
        reply_markup=kb.my_bookings([b.id for b in upcoming], studio.route_url),
    )


def _deadline_text(studio) -> str:
    hours = studio.cancel_deadline_hours
    phone = f" Позвоните в студию: {studio.phone}" if studio.phone else ""
    return texts.DEADLINE.format(hours=hours, word=plural(hours, "часа", "часов", "часов"), phone=phone)


@client_router.callback_query(kb.Mine.filter(F.action == "move"))
async def move_start(callback: CallbackQuery, callback_data: kb.Mine, ctx: BotContext) -> None:
    await callback.answer()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            booking = await logic.own_booking(session, studio.id, callback_data.booking, callback.from_user.id)
        except NotFoundError:
            await callback.message.answer("Запись не найдена.", reply_markup=kb.main_menu())
            return
        if booking.starts_at - datetime.now(UTC) < timedelta(hours=studio.cancel_deadline_hours):
            await callback.message.answer(_deadline_text(studio), reply_markup=kb.after_cancel())
            return
        options = await logic.free_days(session, studio, booking.service_id)
    if not options:
        await callback.message.answer(texts.NO_FREE_DAYS, reply_markup=kb.after_cancel())
        return
    await callback.message.answer(
        f"Выберите новую дату для записи «{texts.e(booking.service_name)} · "
        f"{texts.e(texts.when(booking.starts_at, logic.tz(studio)))}»",
        reply_markup=kb.days(options, booking=booking.id),
    )


@client_router.callback_query(kb.Mine.filter(F.action == "day"))
async def move_day(callback: CallbackQuery, callback_data: kb.Mine, ctx: BotContext) -> None:
    await callback.answer()
    day = date.fromisoformat(callback_data.value)
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        booking = await logic.own_booking(session, studio.id, callback_data.booking, callback.from_user.id)
        starts = await logic.free_starts(session, studio, booking.service_id, day)
    if not starts:
        await callback.message.answer("На этот день время уже разобрали. Выберите другой день.")
        return
    await callback.message.answer(
        f"Свободно: {texts.day_long(day)}.", reply_markup=kb.times(starts, logic.tz(studio), booking=booking.id)
    )


@client_router.callback_query(kb.Mine.filter(F.action == "slot"))
async def move_slot(callback: CallbackQuery, callback_data: kb.Mine, ctx: BotContext) -> None:
    await callback.answer()
    start = datetime.fromtimestamp(int(callback_data.value), tz=UTC)
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            booking = await logic.own_booking(session, studio.id, callback_data.booking, callback.from_user.id)
            booking = await booking_service.reschedule(session, studio.id, booking.id, starts_at=start, actor=CLIENT)
        except SlotUnavailableError:
            await callback.message.answer(texts.SLOT_TAKEN)
            return
        except DeadlinePassedError:
            await callback.message.answer(_deadline_text(studio), reply_markup=kb.after_cancel())
            return
        except AppError as exc:
            await callback.message.answer(exc.message, reply_markup=kb.main_menu())
            return
        when_text = texts.when(booking.starts_at, logic.tz(studio))
    await callback.message.answer(
        f"<b>✓ Запись перенесена</b>\n{texts.e(when_text)}. "
        "Администратор получил уведомление и подтвердит новое время.",
        reply_markup=kb.after_booking(booking.id, studio.route_url),
    )


@client_router.callback_query(kb.Mine.filter(F.action == "cancel"))
async def cancel_ask(callback: CallbackQuery, callback_data: kb.Mine, ctx: BotContext) -> None:
    await callback.answer()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            booking = await logic.own_booking(session, studio.id, callback_data.booking, callback.from_user.id)
        except NotFoundError:
            await callback.message.answer("Запись не найдена.", reply_markup=kb.main_menu())
            return
        hours = studio.cancel_deadline_hours
        text = (
            f"<b>Отменить запись?</b>\n{texts.e(booking.service_name)} · "
            f"{texts.e(texts.when(booking.starts_at, logic.tz(studio)))}\n"
            f"Отменить онлайн можно не позднее чем за {hours} {plural(hours, 'час', 'часа', 'часов')} до визита. "
            "Время освободится для других клиентов."
        )
    await callback.message.answer(text, reply_markup=kb.confirm_cancel(booking.id))


@client_router.callback_query(kb.Mine.filter(F.action == "cancel_yes"))
async def cancel_yes(callback: CallbackQuery, callback_data: kb.Mine, ctx: BotContext) -> None:
    await callback.answer()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        try:
            booking = await logic.own_booking(session, studio.id, callback_data.booking, callback.from_user.id)
            await booking_service.cancel_by_client(session, studio.id, booking.id, actor=CLIENT)
        except DeadlinePassedError:
            await callback.message.answer(_deadline_text(studio), reply_markup=kb.after_cancel())
            return
        except (InvalidTransitionError, NotFoundError) as exc:
            await callback.message.answer(exc.message, reply_markup=kb.main_menu())
            return
    await callback.message.answer(texts.CANCELLED_OK, reply_markup=kb.after_cancel())


@client_router.callback_query(kb.Mine.filter(F.action == "keep"))
async def cancel_keep(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "Запись остаётся в силе. " + texts.SEE_YOU, reply_markup=kb.to_menu([("Мои записи", kb.Menu(action="mine"))])
    )


@client_router.callback_query(kb.Remind.filter())
async def reminder_answer(callback: CallbackQuery, callback_data: kb.Remind, ctx: BotContext) -> None:
    await callback.answer()
    if callback_data.action == "yes":
        await callback.message.answer(texts.SEE_YOU, reply_markup=kb.to_menu())
        return
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        client = await logic.client_by_telegram(session, studio.id, callback.from_user.id)
        if client is not None:
            client.reminders_enabled = False
            await session.commit()
    await callback.message.answer(texts.REMINDERS_OFF, reply_markup=kb.to_menu())


# ---------------------------------------------------------------- questions to the studio


async def _ask_admin(message: Message, state: FSMContext, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
    if not studio.telegram_admin_chat_id:
        phone = f" Позвоните в студию: {studio.phone}" if studio.phone else ""
        await message.answer(texts.NO_ADMIN_CHAT.format(phone=phone), reply_markup=kb.main_menu())
        return
    await state.set_state(Flow.question)
    hours = f": {texts.e(studio.schedule_text)}" if studio.schedule_text else ""
    await message.answer(texts.ASK_ADMIN.format(hours=hours), reply_markup=kb.to_menu())


@client_router.message(Flow.question, F.text)
async def question(message: Message, state: FSMContext, bot: Bot, ctx: BotContext) -> None:
    await state.clear()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        client = await logic.client_by_telegram(session, studio.id, message.from_user.id)
    if not studio.telegram_admin_chat_id:
        await message.answer(texts.NO_ADMIN_CHAT.format(phone=""), reply_markup=kb.main_menu())
        return
    who = texts.e(client.full_name if client else message.from_user.full_name)
    contact = f", {texts.e(client.phone)}" if client else ""
    username = f" @{texts.e(message.from_user.username)}" if message.from_user.username else ""
    await bot.send_message(
        studio.telegram_admin_chat_id,
        f"<b>Вопрос от клиента</b>: {who}{contact}{username}\n\n«{texts.e(message.text[:1500])}»\n\n"
        f"Ответьте на это сообщение, и ответ уйдёт клиенту. #q{message.chat.id}",
    )
    await message.answer(texts.ASK_SENT, reply_markup=kb.main_menu())


# ---------------------------------------------------------------- links from the site


async def _link_site_booking(message: Message, session, studio, token: str) -> None:
    try:
        booking = await booking_service.find_by_manage_token(session, studio.id, token)
    except NotFoundError:
        await message.answer(texts.LINK_FAILED, reply_markup=kb.main_menu())
        return
    client = await session.get(Client, booking.client_id) if booking.client_id else None
    user = message.from_user
    if client is None or (client.telegram_user_id and client.telegram_user_id != user.id):
        await message.answer(texts.LINK_FAILED, reply_markup=kb.main_menu())
        return
    client.telegram_user_id = user.id
    client.telegram_chat_id = message.chat.id
    client.telegram_username = user.username
    await session.commit()
    card = await logic.booking_text(session, studio, booking, f"Запись № {booking.number}")
    await message.answer(texts.LINKED.format(number=booking.number))
    await message.answer(card, reply_markup=kb.after_booking(booking.id, studio.route_url))


# ---------------------------------------------------------------- the studio's admin chat


@admin_router.message(Command("link"))
async def link_admin_chat(message: Message, command: CommandObject, ctx: BotContext) -> None:
    code = (command.args or "").strip()
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
        valid = (
            code
            and studio.telegram_link_code_hash
            and studio.telegram_link_expires_at
            and studio.telegram_link_expires_at > datetime.now(UTC)
            and security.tokens_match(code, studio.telegram_link_code_hash)
        )
        if not valid:
            await message.answer("Код неверный или устарел. Создайте новый в панели: «Настройки», раздел «Связь».")
            return
        studio.telegram_admin_chat_id = message.chat.id
        studio.telegram_link_code_hash = None
        studio.telegram_link_expires_at = None
        await session.commit()
    await message.answer("Чат привязан: сюда будут приходить заявки с сайта и из бота и вопросы клиентов.")


async def _admin_studio(callback: CallbackQuery, session, ctx: BotContext):
    studio = await logic.studio_by_slug(session, ctx.studio_slug)
    if callback.message is None or callback.message.chat.id != studio.telegram_admin_chat_id:
        await callback.answer("Эти кнопки работают только в чате администраторов студии.", show_alert=True)
        return None
    return studio


@admin_router.callback_query(kb.Admin.filter(F.action.in_({"ok", "reject"})))
async def admin_status(callback: CallbackQuery, callback_data: kb.Admin, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await _admin_studio(callback, session, ctx)
        if studio is None:
            return
        target = BookingStatus.CONFIRMED if callback_data.action == "ok" else BookingStatus.CANCELLED
        try:
            await booking_service.change_status(
                session,
                studio.id,
                callback_data.booking,
                target,
                STUDIO_STAFF,
                reason="studio" if target == BookingStatus.CANCELLED else None,
            )
        except (InvalidTransitionError, NotFoundError) as exc:
            await callback.answer(exc.message, show_alert=True)
            return
    label = "✓ Подтверждена" if target == BookingStatus.CONFIRMED else "✕ Отклонена"
    await callback.answer(label)
    panel = ctx.panel_booking_url(studio.id, callback_data.booking)
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n<b>{label}</b> · {texts.e(callback.from_user.full_name)}",
        reply_markup=kb.admin_request(callback_data.booking, panel, can_confirm=False),
    )


@admin_router.callback_query(kb.Admin.filter(F.action == "master"))
async def admin_masters(callback: CallbackQuery, callback_data: kb.Admin, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await _admin_studio(callback, session, ctx)
        if studio is None:
            return
        booking = await session.scalar(
            select(Booking).where(Booking.studio_id == studio.id, Booking.id == callback_data.booking)
        )
        staff = await logic.masters_for(session, studio.id, booking.service_id) if booking else []
    await callback.answer()
    if not staff:
        await callback.message.answer("Для этой услуги нет мастеров с онлайн-записью. Назначьте мастера в панели.")
        return
    await callback.message.edit_reply_markup(
        reply_markup=kb.admin_masters(
            callback_data.booking, staff, ctx.panel_booking_url(studio.id, callback_data.booking)
        )
    )


@admin_router.callback_query(kb.Admin.filter(F.action == "back"))
async def admin_back(callback: CallbackQuery, callback_data: kb.Admin, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await _admin_studio(callback, session, ctx)
        if studio is None:
            return
    await callback.answer()
    panel = ctx.panel_booking_url(studio.id, callback_data.booking)
    await callback.message.edit_reply_markup(reply_markup=kb.admin_request(callback_data.booking, panel))


@admin_router.callback_query(kb.Admin.filter(F.action == "set"))
async def admin_set_master(callback: CallbackQuery, callback_data: kb.Admin, ctx: BotContext) -> None:
    async with ctx.session() as session:
        studio = await _admin_studio(callback, session, ctx)
        if studio is None:
            return
        booking = await session.scalar(
            select(Booking).where(Booking.studio_id == studio.id, Booking.id == callback_data.booking)
        )
        if booking is None:
            await callback.answer("Запись не найдена", show_alert=True)
            return
        try:
            await booking_service.reschedule(
                session,
                studio.id,
                booking.id,
                starts_at=booking.starts_at,
                staff_id=callback_data.staff,
                actor=STUDIO_STAFF,
            )
        except AppError as exc:
            await callback.answer(exc.message, show_alert=True)
            return
        name = await logic.staff_name(session, studio.id, callback_data.staff)
    await callback.answer(f"Мастер: {name}")
    panel = ctx.panel_booking_url(studio.id, callback_data.booking)
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\nМастер: <b>{texts.e(name)}</b>",
        reply_markup=kb.admin_request(callback_data.booking, panel),
    )


async def in_admin_chat(message: Message, bot: Bot, ctx: BotContext) -> bool:
    """Filter: a reply to one of the bot's forwarded questions, written in the studio's admin chat."""
    original = message.reply_to_message
    if original is None or original.from_user is None or original.from_user.id != bot.id:
        return False
    if not QUESTION_TAG.search(original.text or ""):
        return False
    async with ctx.session() as session:
        studio = await logic.studio_by_slug(session, ctx.studio_slug)
    return message.chat.id == studio.telegram_admin_chat_id


@admin_router.message(F.text, in_admin_chat)
async def admin_reply(message: Message, bot: Bot) -> None:
    """An admin answers a forwarded question by replying to it; the answer goes to the client's chat."""
    match = QUESTION_TAG.search(message.reply_to_message.text or "")
    await bot.send_message(int(match.group(1)), f"<b>Ответ администратора</b>\n{texts.e(message.text[:3000])}")
    await message.reply("Ответ отправлен клиенту.")


@client_router.message()
async def fallback(message: Message) -> None:
    await message.answer(texts.UNKNOWN, reply_markup=kb.main_menu())
