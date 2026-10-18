"""Sending messages. The outbox worker only knows this interface, so tests use a fake and never reach Telegram."""

from __future__ import annotations

from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardMarkup


class DeliveryError(Exception):
    def __init__(self, message: str, *, permanent: bool = False, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.permanent = permanent
        self.retry_after = retry_after


class Notifier(Protocol):
    async def send(self, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> None: ...


class TelegramNotifier:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(self, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
        try:
            await self.bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
        except TelegramRetryAfter as exc:
            raise DeliveryError("rate limited", retry_after=exc.retry_after) from exc
        except TelegramForbiddenError as exc:
            # The user blocked the bot or the bot was removed from the chat: retrying will not help.
            raise DeliveryError("forbidden", permanent=True) from exc
        except TelegramBadRequest as exc:
            raise DeliveryError(f"bad request: {exc.message}", permanent=True) from exc
        except (TelegramNetworkError, TelegramServerError) as exc:
            raise DeliveryError(f"telegram unavailable: {exc}") from exc


class RecordingNotifier:
    """Keeps sent messages in memory; used by tests and by a dry run without a token."""

    def __init__(self, fail_with: DeliveryError | None = None) -> None:
        self.sent: list[tuple[int, str, InlineKeyboardMarkup | None]] = []
        self.fail_with = fail_with

    async def send(self, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append((chat_id, text, markup))
