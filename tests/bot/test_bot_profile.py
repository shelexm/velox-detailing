"""The bot fills its description once and keeps texts changed later in @BotFather."""

from __future__ import annotations

from types import SimpleNamespace

from app.bot.__main__ import setup_profile
from app.bot.context import BotContext
from app.models import Studio


class ProfileBot:
    def __init__(self, description: str = "", short: str = "") -> None:
        self.description, self.short = description, short
        self.changed: dict[str, str] = {}

    async def get_my_description(self) -> SimpleNamespace:
        return SimpleNamespace(description=self.description)

    async def get_my_short_description(self) -> SimpleNamespace:
        return SimpleNamespace(short_description=self.short)

    async def set_my_description(self, description: str) -> None:
        self.changed["description"] = description

    async def set_my_short_description(self, short_description: str) -> None:
        self.changed["short"] = short_description


async def test_description_is_filled_once(ctx: BotContext, studio: Studio) -> None:
    empty = ProfileBot()
    await setup_profile(empty, ctx)
    assert empty.changed["description"].startswith(studio.name) and empty.changed["short"]
    assert len(empty.changed["description"]) <= 512 and len(empty.changed["short"]) <= 120

    edited = ProfileBot(description="Свой текст", short="Свой")
    await setup_profile(edited, ctx)
    assert edited.changed == {}
