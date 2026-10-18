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
from app.models import Booking, Client, NotificationOutbox
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
            try:
                for chat_id, text, markup in messages:
                    await notifier.send(chat_id, text, markup)
            except DeliveryError as exc:
                row.attempts += 1
                row.last_error = str(exc)[:500]
                if exc.permanent or row.attempts >= MAX_ATTEMPTS:
                    row.status = OutboxStatus.DEAD
                    logger.warning("outbox %s: gave up (%s)", row.id, exc)
                else:
                    row.status = OutboxStatus.FAILED
                    row.next_attempt_at = now + backoff(row.attempts, exc.retry_after)
                continue
            row.status, row.sent_at, row.last_error = OutboxStatus.SENT, now, None
        await session.commit()
    return len(rows)


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
        try:
            now = datetime.now(UTC)
            if now - last_reminders > timedelta(minutes=5):
                async with ctx.session() as session:
                    await schedule_reminders(session, now=now)
                last_reminders = now
            await deliver_batch(ctx, notifier, now=now)
        except Exception:
            logger.exception("worker iteration failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=3)
