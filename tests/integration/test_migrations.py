import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from tests.conftest import run_alembic


async def test_migrations_roundtrip_and_match_models(settings: Settings, engine: AsyncEngine) -> None:
    await asyncio.to_thread(run_alembic, settings, "downgrade", "base")
    async with engine.connect() as conn:
        tables = (
            (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))).scalars().all()
        )
    assert set(tables) <= {"alembic_version"}

    await asyncio.to_thread(run_alembic, settings, "upgrade", "head")
    # Fails if the models and the migrated schema have drifted apart.
    await asyncio.to_thread(run_alembic, settings, "check")


async def test_btree_gist_extension_is_installed(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        installed = (await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'"))).scalar()
    assert installed == 1
