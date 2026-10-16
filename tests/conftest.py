"""Shared test fixtures.

Tests use their own database (the development database name + "_test"),
which is emptied before every test. The AI is always replaced by FakeAI.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.dependencies import get_db
from app.main import app
from app.routers import conversations
from app.services import ai
from app.services.ai import AIServiceError

DEV_DATABASE_URL = make_url(settings.database_url)
TEST_DATABASE_URL = DEV_DATABASE_URL.set(database=f"{DEV_DATABASE_URL.database}_test")
assert TEST_DATABASE_URL.database != DEV_DATABASE_URL.database


def _create_test_database_if_missing() -> None:
    # Connect to PostgreSQL's built-in "postgres" database to create ours
    admin_engine = create_engine(
        DEV_DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DATABASE_URL.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_URL.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def engine():
    """Create the test database and its tables once per test run."""
    _create_test_database_if_missing()
    engine = create_engine(TEST_DATABASE_URL)
    # The chunks table uses pgvector's halfvec type, so the extension must
    # exist before the tables are created
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    """Empty every table before each test, so each test starts clean."""
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE users, conversations, messages, documents, chunks RESTART IDENTITY CASCADE")
        )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    """A database session for tests to check what was saved."""
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def client(session_factory):
    """A TestClient whose requests use the test database."""

    def get_test_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class FakeAI:
    """Stands in for generate_reply(). Records each call; can be told to fail."""

    def __init__(self):
        self.reply = "This is a fake AI reply."
        self.fail = False
        self.calls = []

    def __call__(self, system_prompt, history):
        self.calls.append({"system_prompt": system_prompt, "history": history})
        if self.fail:
            raise AIServiceError("simulated failure")
        return self.reply


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    """Used automatically by every test, so no test can call the real AI."""
    fake = FakeAI()
    monkeypatch.setattr(conversations, "generate_reply", fake)

    # Safety net: if anything still reaches the real provider, fail loudly
    def real_ai_called(*args, **kwargs):
        raise RuntimeError("A test tried to call the real AI provider")

    monkeypatch.setitem(ai._PROVIDERS, "openrouter", real_ai_called)

    # Embeddings never reach the network either. Failing like a real outage
    # means chat runs its "no store information" fallback in these tests.
    def embedding_unavailable(*args, **kwargs):
        raise AIServiceError("embeddings are disabled in tests")

    monkeypatch.setitem(ai._EMBEDDING_PROVIDERS, "openrouter", embedding_unavailable)
    return fake


@pytest.fixture
def register(client):
    """register(email, password) -> the response from POST /auth/register."""

    def _register(email="alice@example.com", password="correct-horse"):
        return client.post("/auth/register", json={"email": email, "password": password})

    return _register


@pytest.fixture
def auth_headers(client, register):
    """auth_headers(email, password) -> registers and logs in, returns the Bearer header."""

    def _auth_headers(email="alice@example.com", password="correct-horse"):
        assert register(email, password).status_code == 201
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _auth_headers
