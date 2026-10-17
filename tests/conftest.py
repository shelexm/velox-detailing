"""Shared fixtures. Tests only ever run against a database whose name ends with `_test`."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

# Test defaults are applied before any app module reads the environment.
for key, value in {
    "APP_ENV": "test",
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "55432",
    "POSTGRES_DB": "velox_test",
    "POSTGRES_USER": "velox_test",
    "POSTGRES_PASSWORD": "velox_test_only",
    "ALLOWED_HOSTS": "testserver,127.0.0.1,localhost",
    "LOG_LEVEL": "WARNING",
    "TELEGRAM_BOT_TOKEN": "",
}.items():
    os.environ.setdefault(key, value)

import httpx
import pytest
from alembic import command
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.ratelimit import Limiters
from app.db.base import Base
from app.db.migrations import alembic_config
from app.db.session import create_engine, create_sessionmaker
from app.main import create_app


def assert_safe_test_database(settings: Settings) -> None:
    if settings.app_env != "test" or not settings.postgres_db.endswith("_test"):
        raise pytest.UsageError(
            f"Refusing to run tests against database {settings.postgres_db!r} with APP_ENV={settings.app_env!r}: "
            "tests need APP_ENV=test and a database name ending with _test."
        )


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    current = Settings(_env_file=None, media_root=tmp_path_factory.mktemp("media"))
    assert_safe_test_database(current)
    return current


def run_alembic(settings: Settings, *args: str) -> None:
    config = alembic_config()
    config.attributes["database_url"] = settings.database_url
    config.attributes["configure_logger"] = False
    getattr(command, args[0])(config, *args[1:])


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    except OSError as exc:  # connection refused
        pytest.exit(
            f"Test database is not reachable ({exc}). Start it: docker compose -f compose.test.yaml up -d db-test",
            returncode=3,
        )
    await asyncio.to_thread(run_alembic, settings, "upgrade", "head")
    yield engine
    await engine.dispose()


async def truncate_all(engine: AsyncEngine) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    if tables:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def sessionmaker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield create_sessionmaker(engine)
    await truncate_all(engine)


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@pytest.fixture(scope="session")
async def app(settings: Settings, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI, engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app.state.limiters = Limiters()  # rate limits must not leak between tests
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    await truncate_all(engine)
