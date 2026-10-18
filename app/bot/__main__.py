"""Entry point for the Telegram bot process: `python -m app.bot`.

Without TELEGRAM_BOT_TOKEN the process exits at once (code 0): the site and the panel work without the bot.
The token is read from the environment only and never logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, MenuButtonCommands

from app.bot.context import BotContext
from app.bot.handlers import admin_router, client_router
from app.bot.notifier import TelegramNotifier
from app.bot.worker import run_forever
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_sessionmaker

logger = logging.getLogger("app.bot")


def build_dispatcher(ctx: BotContext) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), ctx=ctx)
    # Admin chat handlers first: a reply to a forwarded question must not fall into the client dialog.
    dp.include_router(admin_router)
    dp.include_router(client_router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("update failed", exc_info=event.exception)
        update = event.update
        target = update.message or (update.callback_query.message if update.callback_query else None)
        if target is not None:
            with contextlib.suppress(Exception):
                await target.answer("Что-то пошло не так. Попробуйте ещё раз или нажмите /start.")
        return True

    return dp


async def setup_menu(bot: Bot, ctx: BotContext) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="book", description="Записаться"),
            BotCommand(command="mine", description="Мои записи"),
        ]
    )
    # The calendar Mini App opens from a keyboard button inside the dialog (only that kind of launch can hand
    # the chosen time back to the chat), so the menu button simply lists the commands.
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def run(settings: Settings) -> None:
    engine = create_engine(settings)
    ctx = BotContext(sessionmaker=create_sessionmaker(engine), settings=settings)
    bot = Bot(settings.telegram_bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode="HTML"))
    dp = build_dispatcher(ctx)
    stop = asyncio.Event()
    worker = asyncio.create_task(run_forever(ctx, TelegramNotifier(bot), stop))
    try:
        me = await bot.get_me()
        logger.info("bot @%s started (polling)", me.username)
        await setup_menu(bot, ctx)
        if settings.telegram_use_webhook:
            logger.warning("TELEGRAM_USE_WEBHOOK is not supported yet: falling back to long polling")
        await dp.start_polling(bot, handle_signals=True, allowed_updates=dp.resolve_used_update_types())
    finally:
        stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(worker, timeout=10)
        await bot.session.close()
        await engine.dispose()


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.telegram_bot_token is None:
        logger.warning("TELEGRAM_BOT_TOKEN is not set: the bot is disabled, nothing to run")
        return 0
    asyncio.run(run(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
