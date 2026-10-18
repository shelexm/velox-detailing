"""What every handler needs: database sessions, settings and the studio this bot serves."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings


@dataclass
class BotContext:
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: Settings

    @property
    def studio_slug(self) -> str:
        return self.settings.default_studio_slug

    @property
    def base_url(self) -> str:
        return str(self.settings.public_base_url).rstrip("/")

    @property
    def webapp_enabled(self) -> bool:
        # Telegram opens Mini Apps only over public HTTPS.
        return self.base_url.startswith("https://")

    def panel_booking_url(self, studio_id: int, booking_id: int) -> str:
        return f"{self.base_url}/admin/{studio_id}/bookings/{booking_id}"

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session
