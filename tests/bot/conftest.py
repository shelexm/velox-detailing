"""Bot tests: real database and services, fake Telegram objects (nothing is sent anywhere)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.context import BotContext
from app.core.config import Settings
from app.models import Studio
from app.seed.run import seed_all

USER_ID = 5001
CHAT_ID = 5001
ADMIN_CHAT = -100777


@dataclass
class FakeUser:
    id: int = USER_ID
    first_name: str = "Алексей"
    last_name: str | None = None
    username: str | None = "alexey_test"
    is_bot: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}" if self.last_name else self.first_name


@dataclass
class FakeChat:
    id: int = CHAT_ID
    type: str = "private"


@dataclass
class Contact:
    phone_number: str
    user_id: int | None = USER_ID


@dataclass
class WebAppData:
    data: str


@dataclass
class FakeMessage:
    """Collects everything the bot answers; `answers` holds (text, reply_markup)."""

    text: str | None = None
    from_user: FakeUser = field(default_factory=FakeUser)
    chat: FakeChat = field(default_factory=FakeChat)
    contact: Contact | None = None
    web_app_data: WebAppData | None = None
    reply_to_message: Any = None
    answers: list[tuple[str, Any]] = field(default_factory=list)
    edits: list[tuple[str, Any]] = field(default_factory=list)
    html_text: str = ""

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))

    async def reply(self, text: str, **_: Any) -> None:
        self.answers.append((text, None))

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.edits.append((text, reply_markup))

    async def edit_reply_markup(self, reply_markup: Any = None, **_: Any) -> None:
        self.edits.append(("", reply_markup))

    @property
    def last(self) -> str:
        return self.answers[-1][0]


@dataclass
class FakeCallback:
    message: FakeMessage
    from_user: FakeUser = field(default_factory=FakeUser)
    alerts: list[str] = field(default_factory=list)

    async def answer(self, text: str | None = None, show_alert: bool = False, **_: Any) -> None:
        if text:
            self.alerts.append(text)


class FakeBot:
    id = 42

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: Any) -> None:
        self.sent.append((chat_id, text))


def command(args: str | None = None, name: str = "start") -> CommandObject:
    return CommandObject(prefix="/", command=name, args=args)


def buttons(markup: Any) -> list[Any]:
    return [button for row in markup.inline_keyboard for button in row] if markup is not None else []


@pytest.fixture
async def studio(sessionmaker: async_sessionmaker[AsyncSession]) -> Studio:
    # Tables are emptied by the `sessionmaker` fixture after the test session is closed.
    async with sessionmaker() as session:
        return await seed_all(session)


@pytest.fixture
def ctx(sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> BotContext:
    return BotContext(sessionmaker=sessionmaker, settings=settings)


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=FakeBot.id, chat_id=CHAT_ID, user_id=USER_ID))
