"""Callback data and keyboards. Callback payloads carry ids only (Telegram limits them to 64 bytes)."""

from __future__ import annotations

from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import texts


class Menu(CallbackData, prefix="m"):
    action: str  # book | prices | mine | admin | home


class Pick(CallbackData, prefix="p"):
    kind: str  # group | service | brand | skip | day | slot | back | name
    value: str = ""


class Mine(CallbackData, prefix="b"):
    action: str  # move | cancel | cancel_yes | keep | day | slot | route
    booking: int
    value: str = ""


class Remind(CallbackData, prefix="r"):
    action: str  # yes | stop
    booking: int


class Admin(CallbackData, prefix="a"):
    action: str  # ok | reject | master | set
    booking: int
    staff: int = 0


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Записаться на услугу", callback_data=Menu(action="book"))
    kb.button(text="Посмотреть услуги и цены", callback_data=Menu(action="prices"))
    kb.button(text="Мои записи", callback_data=Menu(action="mine"))
    kb.button(text="Связаться с администратором", callback_data=Menu(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def choices(
    items: list[tuple[str, CallbackData]], *, back: CallbackData | None = None, width: int = 1
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for label, data in items:
        kb.button(text=label, callback_data=data)
    kb.adjust(width)
    if back is not None:
        kb.row(InlineKeyboardButton(text="« Назад", callback_data=back.pack()))
    return kb.as_markup()


def brands() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for brand in texts.BRANDS:
        kb.button(text=brand, callback_data=Pick(kind="brand", value=brand))
    kb.button(text="Другая", callback_data=Pick(kind="brand", value="other"))
    kb.adjust(3)
    kb.row(
        InlineKeyboardButton(text="Без автомобиля", callback_data=Pick(kind="skip").pack()),
        InlineKeyboardButton(text="« Назад", callback_data=Pick(kind="back", value="service").pack()),
    )
    return kb.as_markup()


def days(
    options: list[date], *, prefix: CallbackData | None = None, booking: int | None = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for day in options:
        label = f"{texts.WEEKDAYS_SHORT[day.weekday()]} {day.day}"
        if booking is None:
            kb.button(text=label, callback_data=Pick(kind="day", value=day.isoformat()))
        else:
            kb.button(text=label, callback_data=Mine(action="day", booking=booking, value=day.isoformat()))
    kb.adjust(4)
    back = Pick(kind="back", value="vehicle") if booking is None else Menu(action="mine")
    kb.row(InlineKeyboardButton(text="« Назад", callback_data=back.pack()))
    return kb.as_markup()


def times(starts: list[datetime], tz, *, booking: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for start in starts:
        label = start.astimezone(tz).strftime("%H:%M")
        stamp = str(int(start.timestamp()))
        if booking is None:
            kb.button(text=label, callback_data=Pick(kind="slot", value=stamp))
        else:
            kb.button(text=label, callback_data=Mine(action="slot", booking=booking, value=stamp))
    kb.adjust(3)
    back = Pick(kind="back", value="day") if booking is None else Mine(action="move", booking=booking)
    kb.row(InlineKeyboardButton(text="« Назад", callback_data=back.pack()))
    return kb.as_markup()


def calendar_button(url: str) -> ReplyKeyboardMarkup:
    """The Mini App calendar opens from a reply keyboard button so it can hand the choice back to the chat."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Выбрать дату в календаре", web_app=WebAppInfo(url=url))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def share_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться номером телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="+7 900 000-00-00",
    )


def after_booking(booking_id: int, route_url: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if route_url:
        kb.button(text="Маршрут", url=route_url)
    kb.button(text="Перенести", callback_data=Mine(action="move", booking=booking_id))
    kb.button(text="Отменить", callback_data=Mine(action="cancel", booking=booking_id))
    kb.button(text="Мои записи", callback_data=Menu(action="mine"))
    kb.adjust(2)
    return kb.as_markup()


def my_bookings(upcoming: list[int], route_url: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    single = len(upcoming) == 1
    for booking_id in upcoming[:3]:
        suffix = "" if single else f" № {booking_id}"
        kb.row(
            InlineKeyboardButton(
                text=f"Перенести{suffix}", callback_data=Mine(action="move", booking=booking_id).pack()
            ),
            InlineKeyboardButton(
                text=f"Отменить{suffix}", callback_data=Mine(action="cancel", booking=booking_id).pack()
            ),
        )
    row = []
    if route_url:
        row.append(InlineKeyboardButton(text="Маршрут", url=route_url))
    row.append(InlineKeyboardButton(text="Администратор", callback_data=Menu(action="admin").pack()))
    kb.row(*row)
    kb.row(InlineKeyboardButton(text="Записаться ещё", callback_data=Menu(action="book").pack()))
    return kb.as_markup()


def confirm_cancel(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, отменить", callback_data=Mine(action="cancel_yes", booking=booking_id))
    kb.button(text="Оставить запись", callback_data=Mine(action="keep", booking=booking_id))
    kb.adjust(2)
    return kb.as_markup()


def after_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Записаться снова", callback_data=Menu(action="book"))
    kb.button(text="Администратор", callback_data=Menu(action="admin"))
    kb.adjust(2)
    return kb.as_markup()


def reminder(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Буду", callback_data=Remind(action="yes", booking=booking_id))
    kb.button(text="Перенести", callback_data=Mine(action="move", booking=booking_id))
    kb.button(text="Отменить", callback_data=Mine(action="cancel", booking=booking_id))
    kb.button(text="Не напоминать", callback_data=Remind(action="stop", booking=booking_id))
    kb.adjust(3, 1)
    return kb.as_markup()


def admin_request(booking_id: int, panel_url: str, *, can_confirm: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_confirm:
        kb.button(text="✓ Подтвердить", callback_data=Admin(action="ok", booking=booking_id))
        kb.button(text="Назначить мастера", callback_data=Admin(action="master", booking=booking_id))
        kb.button(text="Отклонить", callback_data=Admin(action="reject", booking=booking_id))
    kb.button(text="Открыть в панели студии ↗", url=panel_url)
    if can_confirm:
        kb.adjust(2, 1, 1)
    else:
        kb.adjust(1)
    return kb.as_markup()


def admin_masters(booking_id: int, staff: list[tuple[int, str]], panel_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for staff_id, name in staff:
        kb.button(text=name, callback_data=Admin(action="set", booking=booking_id, staff=staff_id))
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text="Открыть в панели студии ↗", url=panel_url))
    return kb.as_markup()


def link_only(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])
