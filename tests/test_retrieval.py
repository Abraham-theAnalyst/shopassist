import pytest

from app.core.config import settings
from app.services.ai import AIServiceError
from app.services.retrieval import build_search_text, find_store_information, retrieve
from tests.conftest import vector


def embed_as(query_vector):
    """A fake embedder that returns query_vector for any text."""
    calls = []

    def _embed(texts, mode):
        calls.append((list(texts), mode))
        return [query_vector for _ in texts]

    _embed.calls = calls
    return _embed


def failing_embed(texts, mode):
    raise AIServiceError("simulated outage")


@pytest.fixture
def store(add_document):
    # Cosine similarity to a query of vector(d0=1): A = 1.0, B = 0.8, C = 0.0
    add_document("returns.md", [
        ("Returns > A", vector(d0=1.0)),
        ("Returns > B", vector(d0=0.8, d1=0.6)),
        ("Returns > C", vector(d1=1.0)),
    ])
    add_document("contact.md", [("Contact > Email", vector(d2=1.0)), ("Contact > Hours", vector(d2=1.0))])


@pytest.fixture(autouse=True)
def retrieval_settings(monkeypatch):
    monkeypatch.setattr(settings, "rag_top_k", 4)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    monkeypatch.setattr(settings, "rag_always_include", "contact")


def labels(chunks):
    return [c.label for c in chunks]


def test_search_text_is_the_latest_message_plus_the_previous_one():
    assert build_search_text(["Hi"]) == "Hi"
    assert build_search_text(["one", "two", "three"]) == "two\nthree"


def test_retrieve_embeds_the_search_text_once_as_a_query(db, store):
    embed = embed_as(vector(d0=1.0))

    retrieve(db, "How long is delivery?", embed=embed)

    assert embed.calls == [(["How long is delivery?"], "query")]


def test_chunks_come_most_similar_first_and_below_threshold_are_dropped(db, store):
    chunks = retrieve(db, "question", embed=embed_as(vector(d0=1.0)))

    assert labels(chunks) == ["Returns > A", "Returns > B"]
    assert chunks[0].similarity == pytest.approx(1.0, abs=0.01)
    assert chunks[1].similarity == pytest.approx(0.8, abs=0.01)


def test_at_most_rag_top_k_chunks_are_returned(db, store, monkeypatch):
    monkeypatch.setattr(settings, "rag_top_k", 1)

    assert labels(retrieve(db, "question", embed=embed_as(vector(d0=1.0)))) == ["Returns > A"]


def test_chunks_from_another_embedding_model_are_ignored(db, add_document):
    add_document("old.md", [("Old > Chunk", vector(d0=1.0))], model="some-old-model")

    assert retrieve(db, "question", embed=embed_as(vector(d0=1.0))) == []


def test_contact_document_is_always_included_after_the_relevant_chunks(db, store):
    chunks = find_store_information(db, "question", embed=embed_as(vector(d0=1.0)))

    assert labels(chunks) == ["Returns > A", "Returns > B", "Contact > Email", "Contact > Hours"]
    assert [c.similarity for c in chunks[2:]] == [None, None]


def test_always_included_chunks_are_not_repeated_when_also_retrieved(db, store):
    chunks = find_store_information(db, "question", embed=embed_as(vector(d2=1.0)))

    assert labels(chunks) == ["Contact > Email", "Contact > Hours"]


def test_when_embedding_fails_only_the_always_included_chunks_are_returned(db, store):
    chunks = find_store_information(db, "question", embed=failing_embed)

    assert labels(chunks) == ["Contact > Email", "Contact > Hours"]


def test_always_include_can_be_turned_off(db, store, monkeypatch):
    monkeypatch.setattr(settings, "rag_always_include", "")

    assert find_store_information(db, "question", embed=failing_embed) == []
