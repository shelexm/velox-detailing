"""Admin chat, outbox delivery with retries, reminders and the Mini App signature check."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNotFound,
    TelegramUnauthorizedError,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import handlers as h
from app.bot import keyboards as kb
from app.bot.context import BotContext
from app.bot.notifier import DeliveryError, RecordingNotifier, TelegramNotifier
from app.bot.worker import deliver_batch, schedule_reminders
from app.core import security
from app.core.telegram import InvalidInitData, sign_init_data, verify_init_data
from app.models import Booking, NotificationOutbox, Studio
from app.models.enums import BookingStatus, OutboxStatus
from tests.bot.conftest import ADMIN_CHAT, CHAT_ID, FakeCallback, FakeChat, FakeMessage, buttons, command
from tests.bot.test_bot_flow import book_light_polish


async def _link(session: AsyncSession, studio: Studio, ctx: BotContext) -> None:
    db_studio = await session.get(Studio, studio.id)
    db_studio.telegram_link_code_hash = security.token_hash("CODE-123")
    db_studio.telegram_link_expires_at = datetime.now(UTC) + timedelta(minutes=10)
    await session.commit()
    chat = FakeMessage(chat=FakeChat(id=ADMIN_CHAT, type="supergroup"))
    await h.link_admin_chat(chat, command("WRONG", name="link"), ctx)
    assert "неверный" in chat.last
    await h.link_admin_chat(chat, command("CODE-123", name="link"), ctx)
    assert "Чат привязан" in chat.last
    await session.refresh(db_studio)
    assert db_studio.telegram_admin_chat_id == ADMIN_CHAT and db_studio.telegram_link_code_hash is None


async def test_admin_chat_confirms_and_assigns(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    await _link(session, studio, ctx)
    booking = await book_light_polish(ctx, state, session)

    # The request is delivered to the admin chat with action buttons.
    notifier = RecordingNotifier()
    assert await deliver_batch(ctx, notifier) == 1
    chat_id, text, markup = notifier.sent[0]
    assert chat_id == ADMIN_CHAT and f"Новая заявка № {booking.number}" in text and "из Telegram-бота" in text
    assert "+7 913 452-18-07" in text and "Audi A6, 2021" in text
    assert {b.text for b in buttons(markup)} >= {"✓ Подтвердить", "Отклонить", "Назначить мастера"}

    # Buttons pressed outside the admin chat do nothing.
    outsider = FakeCallback(FakeMessage(chat=FakeChat(id=999)))
    await h.admin_status(outsider, kb.Admin(action="ok", booking=booking.id), ctx)
    assert "только в чате администраторов" in outsider.alerts[0]

    admin_msg = FakeMessage(chat=FakeChat(id=ADMIN_CHAT, type="supergroup"), html_text=text)
    await h.admin_masters(FakeCallback(admin_msg), kb.Admin(action="master", booking=booking.id), ctx)
    masters = [kb.Admin.unpack(b.callback_data) for b in buttons(admin_msg.edits[-1][1]) if b.callback_data]
    # "« Назад" returns the request buttons.
    back = next(m for m in masters if m.action == "back")
    await h.admin_back(FakeCallback(admin_msg), back, ctx)
    assert "✓ Подтвердить" in {b.text for b in buttons(admin_msg.edits[-1][1])}
    masters = [m for m in masters if m.action == "set"]
    chosen = None
    for option in masters:
        pressed = FakeCallback(admin_msg)
        await h.admin_set_master(pressed, option, ctx)
        if pressed.alerts and pressed.alerts[0].startswith("Мастер:"):
            chosen = option
            break
        assert pressed.alerts  # a busy or day-off master is explained, not silently ignored
    assert chosen is not None
    await h.admin_status(FakeCallback(admin_msg), kb.Admin(action="ok", booking=booking.id), ctx)
    assert "✓ Подтверждена" in admin_msg.edits[-1][0]
    await session.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED and booking.staff_id == chosen.staff

    # The client gets the confirmation from the outbox.
    notifier = RecordingNotifier()
    await deliver_batch(ctx, notifier)
    to_client = [m for m in notifier.sent if m[0] == CHAT_ID]
    assert to_client and "Запись подтверждена" in to_client[-1][1]
    again = FakeCallback(admin_msg)
    await h.admin_status(again, kb.Admin(action="ok", booking=booking.id), ctx)
    assert again.alerts  # already confirmed: shown as an alert, nothing changes


async def test_delivery_retries_and_skips(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    booking = await book_light_polish(ctx, state, session)
    # No admin chat yet: the row is skipped, not retried forever.
    assert await deliver_batch(ctx, RecordingNotifier()) == 1
    row = await session.scalar(select(NotificationOutbox).where(NotificationOutbox.booking_id == booking.id))
    await session.refresh(row)
    assert row.status == OutboxStatus.SKIPPED

    await _link(session, studio, ctx)
    await session.execute(update(NotificationOutbox).values(status=OutboxStatus.PENDING))
    await session.commit()
    now = datetime.now(UTC)
    await deliver_batch(ctx, RecordingNotifier(fail_with=DeliveryError("telegram down")), now=now)
    await session.refresh(row)
    assert row.status == OutboxStatus.FAILED and row.attempts == 1 and row.next_attempt_at > now
    # Not due yet: nothing happens.
    sent = RecordingNotifier()
    await deliver_batch(ctx, sent, now=now + timedelta(seconds=5))
    assert sent.sent == []
    await deliver_batch(ctx, sent, now=now + timedelta(minutes=5))
    await session.refresh(row)
    assert row.status == OutboxStatus.SENT and len(sent.sent) == 1

    await session.execute(update(NotificationOutbox).values(status=OutboxStatus.PENDING, attempts=0))
    await session.commit()
    await deliver_batch(
        ctx, RecordingNotifier(fail_with=DeliveryError("blocked", permanent=True)), now=now + timedelta(minutes=6)
    )
    await session.refresh(row)
    assert row.status == OutboxStatus.DEAD


class FailingFor:
    """Fails for one chat with the given exception and records everything else."""

    def __init__(self, chat_id: int, error: Exception) -> None:
        self.chat_id, self.error, self.sent = chat_id, error, []

    async def send(self, chat_id, text, markup=None) -> None:
        if chat_id == self.chat_id:
            raise self.error
        self.sent.append((chat_id, text, markup))


class FailFirst(RecordingNotifier):
    """The first send raises, the rest are recorded."""

    async def send(self, chat_id, text, markup=None) -> None:
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error
        self.sent.append((chat_id, text, markup))


async def test_unexpected_error_fails_one_row_and_keeps_the_rest(
    ctx: BotContext, state, session: AsyncSession, studio: Studio
) -> None:
    await _link(session, studio, ctx)
    booking = await book_light_polish(ctx, state, session)
    await h.cancel_yes(FakeCallback(FakeMessage()), kb.Mine(action="cancel_yes", booking=booking.id), ctx)
    # Two rows for the admin chat now: the new request and its cancellation. The first send breaks.
    notifier = FailFirst(fail_with=RuntimeError("socket closed"))
    now = datetime.now(UTC)
    assert await deliver_batch(ctx, notifier, now=now) == 2
    first, second = await session.scalars(
        select(NotificationOutbox).where(NotificationOutbox.booking_id == booking.id).order_by(NotificationOutbox.id)
    )
    await session.refresh(first)
    await session.refresh(second)
    assert first.status == OutboxStatus.FAILED and first.attempts == 1 and "RuntimeError" in first.last_error
    assert second.status == OutboxStatus.SENT and len(notifier.sent) == 1
    # On the next pass only the failed row goes out: the sent one is not repeated.
    again = RecordingNotifier()
    await deliver_batch(ctx, again, now=now + timedelta(hours=2))
    assert len(again.sent) == 1
    await session.refresh(first)
    assert first.status == OutboxStatus.SENT


async def test_admin_group_migrated_to_supergroup(
    ctx: BotContext, state, session: AsyncSession, studio: Studio
) -> None:
    await _link(session, studio, ctx)
    await book_light_polish(ctx, state, session)
    supergroup = -1001234567890
    await deliver_batch(ctx, FailingFor(ADMIN_CHAT, DeliveryError("migrated", migrate_to=supergroup)))
    db_studio = await session.get(Studio, studio.id)
    await session.refresh(db_studio)
    assert db_studio.telegram_admin_chat_id == supergroup
    notifier = RecordingNotifier()
    await deliver_batch(ctx, notifier)
    assert [m[0] for m in notifier.sent] == [supergroup]


@pytest.mark.parametrize(
    ("error", "permanent", "migrate_to"),
    [
        (TelegramMigrateToChat(method=None, message="migrated", migrate_to_chat_id=-100555), False, -100555),
        (TelegramUnauthorizedError(method=None, message="Unauthorized"), False, None),
        (TelegramNotFound(method=None, message="Not Found"), False, None),
        (TelegramForbiddenError(method=None, message="blocked"), True, None),
    ],
)
async def test_telegram_errors_become_delivery_errors(error, permanent, migrate_to) -> None:
    class Bot:
        async def send_message(self, *args, **kwargs):
            raise error

    with pytest.raises(DeliveryError) as caught:
        await TelegramNotifier(Bot()).send(1, "text")
    assert caught.value.permanent is permanent and caught.value.migrate_to == migrate_to


async def test_reminders(ctx: BotContext, state, session: AsyncSession, studio: Studio) -> None:
    booking = await book_light_polish(ctx, state, session)
    start = datetime.now(UTC) + timedelta(hours=20)
    await session.execute(
        update(Booking)
        .where(Booking.id == booking.id)
        .values(
            starts_at=start,
            ends_at=start + timedelta(hours=8),
            occupied_until=start + timedelta(hours=8, minutes=15),
            created_at=start - timedelta(days=3),
            status=BookingStatus.CONFIRMED,
        )
    )
    await session.commit()
    assert await schedule_reminders(session) == 1
    assert await schedule_reminders(session) == 0  # queued once
    notifier = RecordingNotifier()
    await deliver_batch(ctx, notifier)
    reminder = [m for m in notifier.sent if "НАПОМИНАНИЕ" in m[1]]
    assert reminder and "Завтра в" in reminder[0][1]
    assert {b.text for b in buttons(reminder[0][2])} >= {"Буду", "Перенести", "Отменить", "Не напоминать"}

    # "Не напоминать" turns reminders off for the client.
    chat = FakeMessage()
    await h.reminder_answer(FakeCallback(chat), kb.Remind(action="stop", booking=booking.id), ctx)
    assert "отключены" in chat.last
    start2 = datetime.now(UTC) + timedelta(hours=1, minutes=30)
    await session.execute(
        update(Booking)
        .where(Booking.id == booking.id)
        .values(starts_at=start2, ends_at=start2 + timedelta(hours=8), occupied_until=start2 + timedelta(hours=8))
    )
    await session.commit()
    assert await schedule_reminders(session) == 0


def test_init_data_signature() -> None:
    token = "123456:TEST-TOKEN"
    user = json.dumps({"id": 5001, "first_name": "Алексей", "username": "alexey"})
    signed = sign_init_data({"auth_date": str(int(time.time())), "user": user, "query_id": "AAH"}, token)
    assert verify_init_data(signed, token).id == 5001
    with pytest.raises(InvalidInitData):
        verify_init_data(signed, "123456:OTHER-TOKEN")
    with pytest.raises(InvalidInitData):
        verify_init_data(signed.replace("5001", "5002"), token)
    old = sign_init_data({"auth_date": str(int(time.time()) - 3 * 86400), "user": user}, token)
    with pytest.raises(InvalidInitData):
        verify_init_data(old, token)
    with pytest.raises(InvalidInitData):
        verify_init_data("", token)
