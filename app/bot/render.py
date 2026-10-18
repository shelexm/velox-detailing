"""Turns an outbox row into Telegram messages, using the current state of the booking.

Rows hold ids only; if the booking changed in a way that makes the event pointless (a reminder for a
cancelled visit, a confirmation that was undone), nothing is sent and the row is skipped.
"""

from __future__ import annotations

from datetime import datetime

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import logic, texts
from app.bot.context import BotContext
from app.core.phone import format_ru_phone
from app.models import Booking, Client, NotificationOutbox, Studio
from app.models.enums import BookingStatus
from app.services.outbox import AUDIENCE_ADMINS

Message = tuple[int, str, InlineKeyboardMarkup | None]
ACTIVE = (BookingStatus.NEW, BookingStatus.CONFIRMED)


def _admin_fields(booking: Booking, client: Client | None, studio: Studio, staff: str | None, box: str | None) -> str:
    tz = logic.tz(studio)
    lines = [f"Клиент: {texts.e(booking.contact_name or (client.full_name if client else ''))}"]
    if client:
        lines.append(f"Телефон: <code>{texts.e(format_ru_phone(client.phone))}</code>")
        if client.telegram_username:
            lines.append(f"Telegram: @{texts.e(client.telegram_username)}")
    if booking.vehicle_description:
        lines.append(f"Автомобиль: {texts.e(booking.vehicle_description)}")
    lines.append(f"Услуга: {texts.e(booking.service_name)}")
    lines.append(
        f"Когда: <code>{texts.e(texts.when(booking.starts_at, tz))}{' · ' + texts.e(box) if box else ''}</code>"
    )
    lines.append(f"Мастер: {texts.e(staff) if staff else 'не назначен'}")
    if booking.client_comment:
        lines.append(f"Комментарий: «{texts.e(booking.client_comment)}»")
    return "\n".join(lines)


async def render(session: AsyncSession, ctx: BotContext, row: NotificationOutbox) -> list[Message]:
    studio = await session.get(Studio, row.studio_id)
    booking = await session.get(Booking, row.booking_id) if row.booking_id else None
    if studio is None or booking is None:
        return []
    client = await session.get(Client, booking.client_id) if booking.client_id else None
    staff = await logic.staff_name(session, studio.id, booking.staff_id)
    tz = logic.tz(studio)
    panel = ctx.panel_booking_url(studio.id, booking.id)

    if row.audience == AUDIENCE_ADMINS:
        chat = studio.telegram_admin_chat_id
        if not chat:
            return []
        box = None
        if booking.resource_id:
            from app.models import Resource

            resource = await session.get(Resource, booking.resource_id)
            box = resource.name if resource else None
        fields = _admin_fields(booking, client, studio, staff, box)
        if row.event == "booking_created":
            source = texts.SOURCES.get(booking.source, "")
            title = f"<b>Новая заявка № {booking.number}</b> · {source}"
            return [
                (
                    chat,
                    f"{title}\n{fields}",
                    kb.admin_request(booking.id, panel, can_confirm=booking.status == BookingStatus.NEW),
                )
            ]
        if row.event == "booking_rescheduled":
            previous = row.payload.get("previous_start")
            was = texts.when(datetime.fromisoformat(previous), tz) if previous else ""
            title = f"<b>Клиент перенёс запись № {booking.number}</b>" + (
                f"\nБыло: <s>{texts.e(was)}</s>" if was else ""
            )
            return [
                (
                    chat,
                    f"{title}\n{fields}",
                    kb.admin_request(booking.id, panel, can_confirm=booking.status == BookingStatus.NEW),
                )
            ]
        if row.event == "booking_cancelled":
            return [
                (
                    chat,
                    f"<b>Клиент отменил запись № {booking.number}</b>\n{fields}",
                    kb.link_only("Открыть в панели студии ↗", panel),
                )
            ]
        return []

    chat = client.telegram_chat_id if client else None
    if not chat:
        return []
    local = booking.starts_at.astimezone(tz)
    route = studio.route_url
    if row.event == "booking_confirmed":
        if booking.status != BookingStatus.CONFIRMED:
            return []
        master = f" Мастер: {texts.e(staff)}." if staff else ""
        text = (
            "<b>✓ Запись подтверждена</b>\n"
            f"Ждём вас в {texts.WEEKDAYS_ACC[local.weekday()]}, {local.day} {texts.MONTHS_GEN[local.month - 1]}, "
            f"в {local:%H:%M}.{master}\nВозьмите с собой ключ и документы на автомобиль."
        )
        return [(chat, text, kb.after_booking(booking.id, route))]
    if row.event == "booking_cancelled":
        text = (
            f"<b>Запись № {booking.number} отменена студией</b>\n{texts.e(booking.service_name)}, "
            f"{texts.e(texts.when(booking.starts_at, tz))}. Напишите нам, подберём другое время."
        )
        return [(chat, text, kb.after_cancel())]
    if row.event == "booking_rescheduled":
        if booking.status not in ACTIVE:
            return []
        card = await logic.booking_text(session, studio, booking, "Время записи изменено")
        return [(chat, card, kb.after_booking(booking.id, route))]
    if row.event == "booking_created":
        if booking.status not in ACTIVE:
            return []
        card = await logic.booking_text(session, studio, booking, f"Вы записаны: № {booking.number}")
        return [(chat, card, kb.after_booking(booking.id, route))]
    if row.event in ("reminder_24h", "reminder_2h"):
        planned = row.payload.get("starts_at")
        if booking.status not in ACTIVE or not client.reminders_enabled:
            return []
        if planned and planned != booking.starts_at.isoformat():
            return []  # the visit moved; the new time gets its own reminder
        day = "Завтра" if row.event == "reminder_24h" else "Сегодня"
        vehicle = f" для {texts.e(booking.vehicle_description)}" if booking.vehicle_description else ""
        place = logic.address(studio)
        where = f" Студия: {texts.e(place)}." if place else ""
        text = (
            f"<code>НАПОМИНАНИЕ</code>\n{day} в {local:%H:%M}: {texts.e(booking.service_name.lower())}{vehicle}.{where}"
        )
        return [(chat, text, kb.reminder(booking.id))]
    return []
