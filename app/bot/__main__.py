"""Entry point for the Telegram bot process: `python -m app.bot`."""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("app.bot")


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.telegram_bot_token is None:
        logger.warning("TELEGRAM_BOT_TOKEN is not set: the bot is disabled, nothing to run")
        return 0
    logger.info("Telegram bot is not implemented yet in this build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
