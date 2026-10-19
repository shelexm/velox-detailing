"""Domain errors and the single JSON error format: {"error": {"code", "message", "details"}, "request_id"}.

Messages are user-facing (Russian). Stack traces never leave the server.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Некорректный запрос"

    def __init__(self, message: str | None = None, *, code: str | None = None, details: Any = None) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Не найдено"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Конфликт данных"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_error"
    message = "Проверьте введённые данные"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Требуется вход"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "Недостаточно прав"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Слишком много попыток. Попробуйте позже"


_HTTP_CODES = {
    400: ("bad_request", "Некорректный запрос"),
    401: ("unauthorized", "Требуется вход"),
    403: ("forbidden", "Недостаточно прав"),
    404: ("not_found", "Не найдено"),
    405: ("method_not_allowed", "Метод не поддерживается"),
    413: ("payload_too_large", "Слишком большой запрос"),
    429: ("rate_limited", "Слишком много запросов"),
}


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error, "request_id": request_id_var.get()}


def _respond(request: Request, status: int, code: str, message: str, details: Any = None) -> Response:
    renderer = getattr(request.app.state, "html_error_renderer", None)
    wants_html = "text/html" in request.headers.get("accept", "")
    if renderer is not None and wants_html and not request.url.path.startswith(("/api/", "/health")):
        return renderer(request, status, message)
    return JSONResponse(error_body(code, message, details), status_code=status)


_RU_MESSAGES: dict[str, str] = {
    "missing": "Обязательное поле",
    "string_too_short": "Слишком коротко: минимум {min_length} симв.",
    "string_too_long": "Слишком длинно: максимум {max_length} симв.",
    "too_short": "Слишком мало: минимум {min_length}",
    "too_long": "Слишком много: максимум {max_length}",
    "greater_than_equal": "Не меньше {ge}",
    "greater_than": "Больше {gt}",
    "less_than_equal": "Не больше {le}",
    "less_than": "Меньше {lt}",
    "int_parsing": "Введите целое число",
    "int_type": "Введите целое число",
    "int_from_float": "Введите целое число",
    "float_parsing": "Введите число",
    "float_type": "Введите число",
    "bool_parsing": "Нужно значение «да» или «нет»",
    "bool_type": "Нужно значение «да» или «нет»",
    "string_type": "Нужен текст",
    "enum": "Недопустимое значение",
    "literal_error": "Недопустимое значение",
    "extra_forbidden": "Лишнее поле",
    "date_parsing": "Некорректная дата",
    "date_type": "Некорректная дата",
    "date_from_datetime_parsing": "Некорректная дата",
    "datetime_parsing": "Некорректные дата и время",
    "datetime_type": "Некорректные дата и время",
    "time_parsing": "Некорректное время",
    "json_invalid": "Некорректные данные",
    "url_parsing": "Некорректный адрес",
}


def russian_message(err: Mapping[str, Any]) -> str:
    """The text of one pydantic error for a person: Russian for the built-in checks, ours kept as written."""
    template = _RU_MESSAGES.get(str(err.get("type", "")))
    if template is None:
        return str(err.get("msg", "")).removeprefix("Value error, ")
    try:
        return template.format(**(err.get("ctx") or {}))
    except (KeyError, IndexError):
        return str(err.get("msg", ""))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> Response:
        return _respond(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> Response:
        # Only location, message and type: the submitted values may contain personal data.
        details = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")),
                "message": russian_message(err),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return _respond(request, 422, "validation_error", "Проверьте введённые данные", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> Response:
        code, message = _HTTP_CODES.get(exc.status_code, ("http_error", "Ошибка запроса"))
        response = _respond(request, exc.status_code, code, message)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> Response:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _respond(request, 500, "internal_error", "Внутренняя ошибка сервера. Попробуйте ещё раз")
