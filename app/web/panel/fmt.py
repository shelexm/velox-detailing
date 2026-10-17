"""Russian date and time labels used across the panel templates."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.web.templating import plural

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)  # fmt: skip


def hm(moment: datetime | None) -> str:
    return moment.strftime("%H:%M") if moment else ""


def day_short(day: date) -> str:
    """Пн, 19.10"""
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {day:%d.%m}"


def day_long(day: date) -> str:
    """19 октября, пн"""
    return f"{day.day} {MONTHS_GEN[day.month - 1]}, {WEEKDAYS_SHORT[day.weekday()].lower()}"


def date_caption(day: date) -> str:
    """СУББОТА · 17 ОКТЯБРЯ 2026"""
    return f"{WEEKDAYS[day.weekday()]} · {day.day} {MONTHS_GEN[day.month - 1]} {day.year}".upper()


def duration(minutes: int | float) -> str:
    minutes = round(minutes)
    if minutes < 60:
        return f"{minutes} мин"
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return f"{hours} ч"
    if rest == 30:
        return f"{hours},5 ч"
    return f"{hours} ч {rest} мин"


def ago(moment: datetime, now: datetime) -> str:
    delta = now - moment
    if delta < timedelta(minutes=1):
        return "только что"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)} мин назад"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)} ч назад"
    days = delta.days
    return f"{days} {plural(days, 'день', 'дня', 'дней')} назад"


def greeting(now: datetime) -> str:
    if 5 <= now.hour < 12:
        return "Доброе утро"
    if 12 <= now.hour < 18:
        return "Добрый день"
    if 18 <= now.hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def relative_day(day: date, today: date) -> str:
    if day == today:
        return "сегодня"
    if day == today + timedelta(days=1):
        return "завтра"
    return day_short(day)


FILTERS = {
    "hm": hm,
    "day_short": day_short,
    "day_long": day_long,
    "date_caption": date_caption,
    "duration": duration,
}
