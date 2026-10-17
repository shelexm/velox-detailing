import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_development_defaults_are_insecure_only_outside_production() -> None:
    settings = make(app_env="development")
    assert settings.cookie_secure is False
    assert make(app_env="production", postgres_password="x" * 20).cookie_secure is True


def test_production_rejects_weak_configuration() -> None:
    with pytest.raises(ValidationError) as error:
        make(app_env="production", postgres_password="short", cookie_secure=False, allowed_hosts="*")
    message = str(error.value)
    assert "POSTGRES_PASSWORD" in message
    assert "COOKIE_SECURE" in message
    assert "ALLOWED_HOSTS" in message


def test_allowed_hosts_accepts_comma_separated_list() -> None:
    settings = make(allowed_hosts="example.com, *.trycloudflare.com ,")
    assert settings.allowed_hosts == ["example.com", "*.trycloudflare.com"]


def test_empty_telegram_token_disables_bot() -> None:
    assert make(telegram_bot_token="").telegram_bot_token is None


def test_secrets_are_hidden_from_repr_and_url() -> None:
    settings = make(
        postgres_password="super-secret-value", telegram_bot_token="123456:ABCdefGhIJKlmnoPQRstuVWXyz0123456789"
    )
    rendered = repr(settings) + str(settings.database_url)
    assert "super-secret-value" not in rendered
    assert "ABCdef" not in rendered
    assert settings.database_url.password == "super-secret-value"
