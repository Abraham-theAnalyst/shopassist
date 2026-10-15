import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "given, expected",
    [
        # Neon style: plain postgresql:// with SSL options
        (
            "postgresql://user:pw@ep-example.neon.tech/neondb?sslmode=require&channel_binding=require",
            "postgresql+psycopg://user:pw@ep-example.neon.tech/neondb?sslmode=require&channel_binding=require",
        ),
        # Older postgres:// style
        ("postgres://user:pw@host:5432/db", "postgresql+psycopg://user:pw@host:5432/db"),
        # Already correct: left alone
        ("postgresql+psycopg://user:pw@db:5432/db", "postgresql+psycopg://user:pw@db:5432/db"),
    ],
)
def test_database_url_uses_psycopg_driver(given, expected):
    settings = Settings(database_url=given, jwt_secret_key="test", ai_model="test")

    assert settings.database_url == expected


def test_settings_error_does_not_show_secret_values(monkeypatch):
    # Simulate a deployment where AI_MODEL is missing
    monkeypatch.delenv("AI_MODEL", raising=False)
    # Short on purpose: pydantic shortens long values in errors, which could
    # hide a leak in this test while still printing part of a real secret
    secret = "s3cr3t"

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, jwt_secret_key=secret, database_url="postgresql://u:p@h/db")

    message = str(error.value)
    assert "ai_model" in message  # the error still names the missing setting
    assert secret not in message
    assert "input_value" not in message  # no input values printed at all
