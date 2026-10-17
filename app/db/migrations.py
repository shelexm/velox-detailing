"""Helpers around the Alembic configuration shared by the app, the CLI and tests."""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import BASE_DIR


def alembic_config() -> Config:
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return config


def migration_heads() -> tuple[str, ...]:
    return tuple(ScriptDirectory.from_config(alembic_config()).get_heads())
