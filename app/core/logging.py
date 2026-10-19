"""Logging setup: one line per record, request id attached, personal data and tokens masked."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_PHONE = re.compile(r"(?<!\d)(\+?7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*(\d{2})(?!\d)")
_TELEGRAM_TOKEN = re.compile(r"(?<![0-9])\d{6,12}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_-])")  # also in .../bot<token>/getMe
# The secret link of a booking: /booking/<token> and /bookings/manage/<token>[/...] end up in access logs.
_MANAGE_TOKEN = re.compile(r"(/(?:booking|bookings/manage)/)[A-Za-z0-9_-]{16,}")
_SECRET_PAIR = re.compile(r"(?i)(password|token|secret|cookie|authorization)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",;]+")


def mask_sensitive(text: str) -> str:
    """Hide phone numbers (keep the last two digits), bot tokens, booking links and key=value secrets."""
    text = _TELEGRAM_TOKEN.sub("<telegram-token>", text)
    text = _MANAGE_TOKEN.sub(r"<token>", text)
    text = _PHONE.sub(lambda m: f"+7*******{m.group(2)}", text)
    return _SECRET_PAIR.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class QuietProbeFilter(logging.Filter):
    """The container healthcheck calls /health/live every 15 s; its access lines would drown the real ones."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (isinstance(args, tuple) and len(args) >= 3 and str(args[2]).startswith("/health/live"))


class MaskingFormatter(logging.Formatter):
    """Masks the fully formatted line, including exception tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return mask_sensitive(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(MaskingFormatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Uvicorn and aiogram install their own handlers; route them through the masking handler instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiogram"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").addFilter(QuietProbeFilter())
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
