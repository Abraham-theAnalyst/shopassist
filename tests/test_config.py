import pytest

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
