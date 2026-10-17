"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent.parent

Environment = Literal["development", "test", "production"]


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Environment = "development"
    app_name: str = "VÉLOX Detailing Studio"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "velox"
    postgres_user: str = "velox"
    postgres_password: SecretStr = SecretStr("")
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)

    public_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")
    allowed_hosts: Annotated[list[str], NoDecode] = ["127.0.0.1", "localhost"]
    cookie_secure: bool | None = None
    session_ttl_hours: int = Field(default=12, ge=1, le=24 * 30)

    default_studio_slug: str = "velox"
    media_root: Path = BASE_DIR / "media"

    telegram_bot_token: SecretStr | None = None
    telegram_use_webhook: bool = False

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _parse_hosts(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def _empty_token_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.cookie_secure is None:
            self.cookie_secure = self.app_env == "production"
        if self.app_env == "production":
            problems = []
            if len(self.postgres_password.get_secret_value()) < 16:
                problems.append("POSTGRES_PASSWORD must be at least 16 characters in production")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must not be disabled in production")
            if "*" in self.allowed_hosts:
                problems.append("ALLOWED_HOSTS must list explicit hosts in production")
            if problems:
                raise ValueError("; ".join(problems))
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
