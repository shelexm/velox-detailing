"""Bot message texts (Telegram HTML). Every value that comes from people is escaped here."""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from app.models.enums import BookingSource, BookingStatus
from app.web.templating import plural, rub

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
WEEKDAYS_ACC = ("понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье")
WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
SOURCES = {
    BookingSource.SITE: "с сайта",
    BookingSource.TELEGRAM: "из Telegram-бота",
    BookingSource.ADMIN: "из панели",
    BookingSource.PHONE: "по телефону",
}
STATUSES = {
    BookingStatus.NEW: "ждёт подтверждения",
    BookingStatus.CONFIRMED: "подтверждена",
    BookingStatus.DONE: "завершена",
    BookingStatus.NO_SHOW: "неявка",
    BookingStatus.CANCELLED: "отменена",
}
BRANDS = ("BMW", "Mercedes", "Audi", "Porsche", "Lexus", "Toyota", "Volkswagen", "Kia")


def e(value: object) -> str:
    return escape(str(value), quote=False) if value is not None else ""


def day_short(day: date) -> str:
    """Ср, 21.10"""
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {day:%d.%m}"


def day_long(day: date) -> str:
    """среда, 21 октября"""
    return f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS_GEN[day.month - 1]}"


def when(moment: datetime, tz: ZoneInfo) -> str:
    """Ср, 21 октября · 12:00"""
    local = moment.astimezone(tz)
    return f"{WEEKDAYS_SHORT[local.weekday()]}, {local.day} {MONTHS_GEN[local.month - 1]} · {local:%H:%M}"


def duration_text(label: str | None, minutes: int | None, days: int | None) -> str:
    if label:
        return label
    if days:
        return f"{days} {plural(days, 'день', 'дня', 'дней')}"
    if minutes:
        hours, rest = divmod(minutes, 60)
        if not hours:
            return f"{rest} мин"
        return f"{hours} ч" + (f" {rest} мин" if rest else "")
    return ""


WELCOME = (
    "<b>{name}</b>\n"
    "Приветствуем! Подберём услугу для вашего автомобиля и поможем записаться.\n\n"
    "Выберите, с чего начать:"
)
STEP_SERVICE = (
    "<code>ШАГ 1 ИЗ 4 · УСЛУГА</code>\n"
    "Что нужно автомобилю? Цены ориентировочные: точную сумму мастер назовёт после осмотра."
)
STEP_VARIANT = "<code>ШАГ 1 ИЗ 4 · УСЛУГА</code>\n<b>{group}</b>: выберите вариант."
STEP_VEHICLE = "<code>ШАГ 2 ИЗ 4 · АВТОМОБИЛЬ</code>\nВыберите марку или напишите марку и модель одним сообщением."
STEP_VEHICLE_MODEL = "Напишите модель и год, например «{brand} A6, 2021». Или нажмите «Пропустить»."
STEP_DAY = "<b>{vehicle}записали.</b>\n{service} занимает {duration}, ориентир {price}. Теперь выберем дату."
STEP_DAY_NO_CAR = "{service} занимает {duration}, ориентир {price}. Теперь выберем дату."
STEP_TIME = "Свободно: {day}. Выберите время."
NO_FREE_DAYS = "В ближайшие дни свободного времени нет. Напишите администратору, подберём вариант."
HOLD_TAKEN = "<b>{when}</b>\nВремя удерживается за вами {minutes} минут, пока вы завершаете запись."
STEP_NAME = "<code>ШАГ 4 ИЗ 4 · КОНТАКТЫ</code>\nКак к вам обращаться?"
STEP_PHONE = "Приятно познакомиться, {name}! Отправьте номер телефона: по нему администратор подтвердит запись."
PHONE_HINT = "Нажмите «Поделиться номером» или напишите номер в формате +7 900 000-00-00."
CONSENT = "Отправляя номер, вы соглашаетесь с политикой обработки данных: {url}"
HOLD_EXPIRED = "Время удержания истекло, слот мог занять кто-то другой. Выберите время заново."
SLOT_TAKEN = "Это время только что заняли. Выберите другое."
ASK_ADMIN = "Напишите вопрос одним сообщением: передадим администратору. Ответ придёт сюда в рабочее время{hours}."
ASK_SENT = "Вопрос передан администратору."
NO_ADMIN_CHAT = "Чат с администратором пока не подключён.{phone}"
CANCELLED_OK = "Запись отменена. Будем рады видеть вас снова."
DEADLINE = "Изменить запись онлайн уже нельзя: до визита меньше {hours} {word}.{phone}"
NOTHING_UPCOMING = "Предстоящих записей нет."
LINKED = "Готово: уведомления о записи № {number} будут приходить сюда."
LINK_FAILED = "Ссылка устарела или запись не найдена. Откройте её ещё раз из письма или с сайта."
REMINDERS_OFF = "Напоминания отключены. Включить снова можно, написав администратору."
SEE_YOU = "Отлично, ждём вас!"
UNKNOWN = "Не понял сообщение. Нажмите «Меню» или /start."


def booking_card(
    *,
    title: str,
    service: str,
    when_text: str,
    vehicle: str | None,
    staff: str | None,
    price: int | None,
    duration: str,
    address: str | None,
    status: BookingStatus | None = None,
    footer: str = "",
) -> str:
    lines = [f"<b>{e(title)}</b>" + (f" · <i>{STATUSES.get(status, '')}</i>" if status in STATUSES else "")]
    lines.append(f"Услуга: {e(service)}")
    if vehicle:
        lines.append(f"Автомобиль: {e(vehicle)}")
    lines.append(f"Когда: <code>{e(when_text)}</code>")
    lines.append(f"Мастер: {e(staff) if staff else 'назначит администратор'}")
    if price is not None or duration:
        lines.append(f"Ориентир: {e(' · '.join(x for x in (rub(price) if price is not None else '', duration) if x))}")
    if address:
        lines.append(f"Адрес: {e(address)}")
    if footer:
        lines.extend(["", footer])
    return "\n".join(lines)


def price_text(price: int | None) -> str:
    return rub(price) if price is not None else "по запросу"
