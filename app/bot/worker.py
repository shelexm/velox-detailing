"""Background jobs of the bot process: outbox delivery with retries and reminder scheduling."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.context import BotContext
from app.bot.notifier import DeliveryError, Notifier
from app.bot.render import render
from app.models import Booking, Client, NotificationOutbox, Studio
from app.models.enums import BookingStatus, OutboxStatus
from app.services import outbox

logger = logging.getLogger("app.bot.worker")
MAX_ATTEMPTS = 8
BATCH = 20
# kind, lead time before the visit, the latest moment it still makes sense to send it
REMINDERS = (
    ("reminder_24h", timedelta(hours=24), timedelta(hours=3)),
    ("reminder_2h", timedelta(hours=2), timedelta(minutes=30)),
)


def backoff(attempts: int, retry_after: int | None = None) -> timedelta:
    if retry_after:
        return timedelta(seconds=retry_after + 1)
    return timedelta(seconds=min(30 * 2 ** (attempts - 1), 3600))


async def deliver_batch(ctx: BotContext, notifier: Notifier, *, now: datetime | None = None) -> int:
    """Sends due outbox rows once. Rows are locked with SKIP LOCKED, so two workers never send the same row."""
    now = now or datetime.now(UTC)
    async with ctx.session() as session:
        rows = list(
            await session.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)),
                    NotificationOutbox.next_attempt_at <= now,
                )
                .order_by(NotificationOutbox.id)
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            try:
                messages = await render(session, ctx, row)
            except Exception:  # a broken row must not stop the others
                logger.exception("outbox %s: cannot render", row.id)
                row.status, row.last_error = OutboxStatus.DEAD, "render failed"
                continue
            if not messages:
                row.status = OutboxStatus.SKIPPED
                continue
            chat_id = None
            try:
                for chat_id, text, markup in messages:
                    await notifier.send(chat_id, text, markup)
            except DeliveryError as exc:
                if exc.migrate_to is not None and await _follow_migration(session, row, chat_id, exc.migrate_to):
                    # Admin chat id updated: the same row goes to the supergroup on the next pass.
                    row.status, row.last_error = OutboxStatus.FAILED, str(exc)[:500]
                    continue
                _failed(row, now, str(exc), permanent=exc.permanent, retry_after=exc.retry_after)
                continue
            except Exception as exc:
                # Anything unexpected counts as one attempt of this row only. Letting it escape would roll back
                # the whole batch: messages already sent would go out again every few seconds.
                logger.exception("outbox %s: unexpected delivery error", row.id)
                _failed(row, now, f"{type(exc).__name__}: {exc}")
                continue
            row.status, row.sent_at, row.last_error = OutboxStatus.SENT, now, None
        await session.commit()
    return len(rows)


def _failed(
    row: NotificationOutbox, now: datetime, error: str, *, permanent: bool = False, retry_after: int | None = None
) -> None:
    row.attempts += 1
    row.last_error = error[:500]
    if permanent or row.attempts >= MAX_ATTEMPTS:
        row.status = OutboxStatus.DEAD
        logger.warning("outbox %s: gave up (%s)", row.id, error)
    else:
        row.status = OutboxStatus.FAILED
        row.next_attempt_at = now + backoff(row.attempts, retry_after)


async def _follow_migration(
    session: AsyncSession, row: NotificationOutbox, old_chat: int | None, new_chat: int
) -> bool:
    """The admin group became a supergroup: Telegram gives its new id, keep the studio linked to it."""
    if old_chat is None:
        return False
    studio = await session.get(Studio, row.studio_id)
    if studio is None or studio.telegram_admin_chat_id != old_chat:
        return False
    studio.telegram_admin_chat_id = new_chat
    logger.info("studio %s: admin chat migrated to a supergroup", studio.id)
    return True


async def schedule_reminders(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Queues reminders 24 h and 2 h before visits; each (booking, start time, kind) is queued once."""
    now = now or datetime.now(UTC)
    queued = 0
    for kind, lead, latest in REMINDERS:
        rows = await session.execute(
            select(Booking)
            .join(Client, and_(Client.id == Booking.client_id, Client.studio_id == Booking.studio_id))
            .where(
                Booking.status.in_((BookingStatus.NEW, BookingStatus.CONFIRMED)),
                Booking.starts_at > now + latest,
                Booking.starts_at <= now + lead,
                # Booked shortly before the visit: the earlier reminder would only repeat the confirmation.
                Booking.created_at <= Booking.starts_at - lead,
                Client.reminders_enabled.is_(True),
                Client.telegram_chat_id.is_not(None),
            )
        )
        for (booking,) in rows.all():
            key = f"{kind}:{booking.id}:{int(booking.starts_at.timestamp())}"
            exists = await session.scalar(
                select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == f"{key}:{outbox.AUDIENCE_CLIENT}")
            )
            if exists:
                continue
            await outbox.enqueue(
                session,
                booking,
                kind,
                audiences=(outbox.AUDIENCE_CLIENT,),
                extra={"starts_at": booking.starts_at.isoformat()},
                dedupe_key=key,
            )
            queued += 1
    await session.commit()
    return queued


async def run_forever(ctx: BotContext, notifier: Notifier, stop: asyncio.Event) -> None:
    last_reminders = datetime.min.replace(tzinfo=UTC)
    while not stop.is_set():
        now = datetime.now(UTC)
        # Separate guards: a failing reminder query must not stop delivery, and the other way round.
        if now - last_reminders > timedelta(minutes=5):
            try:
                async with ctx.session() as session:
                    await schedule_reminders(session, now=now)
            except Exception:
                logger.exception("reminder scheduling failed")
            last_reminders = now
        try:
            await deliver_batch(ctx, notifier, now=now)
        except Exception:
            logger.exception("outbox delivery failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=3)
