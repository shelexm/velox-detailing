"""Password hashing (Argon2id), opaque session tokens, CSRF tokens and response security headers."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_COOKIE = "velox_session"
CSRF_COOKIE = "velox_csrf"
CSRF_HEADER = "x-csrf-token"
MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()
# Verified against when the e-mail is unknown, so both cases take the same time.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
    if password.strip() != password or len(set(password)) < 5:
        raise ValueError("Пароль слишком простой")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str | None, expected_hash: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(token_hash(token), expected_hash)


CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        # Inline style attributes only (focal points of photos); style elements stay restricted.
        "style-src-attr 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
# The Telegram Mini App page is embedded by Telegram clients and needs their small bridge script.
CSP_TELEGRAM_APP = CSP.replace("frame-ancestors 'none'", "frame-ancestors https://web.telegram.org").replace(
    "script-src 'self'", "script-src 'self' https://telegram.org"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        is_https = scope.get("scheme") == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in headers}
                csp = CSP_TELEGRAM_APP if path.startswith("/tg/") else CSP
                extra = [
                    (b"content-security-policy", csp.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                ]
                if not path.startswith("/tg/"):
                    extra.append((b"x-frame-options", b"DENY"))
                if is_https:
                    extra.append((b"strict-transport-security", b"max-age=31536000"))
                if path.startswith(("/api/v1/admin", "/api/v1/auth", "/admin")) and b"cache-control" not in present:
                    extra.append((b"cache-control", b"no-store"))
                if path.startswith("/admin"):
                    extra.append((b"x-robots-tag", b"noindex, nofollow"))
                headers.extend(item for item in extra if item[0] not in present)
            await send(message)

        await self.app(scope, receive, send_with_headers)
