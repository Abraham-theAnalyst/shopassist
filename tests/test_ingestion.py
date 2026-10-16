import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Chunk, Document
from app.services.ai import AIServiceError
from app.services.ingestion import ingest_knowledge
from tests.conftest import vector


class FakeEmbedder:
    """Returns a fake vector per text and records each call (no network)."""

    def __init__(self):
        self.calls = []
        self.fail = False

    def __call__(self, texts, mode):
        self.calls.append((list(texts), mode))
        if self.fail:
            raise AIServiceError("simulated outage")
        return [vector(d0=1.0) for _ in texts]


@pytest.fixture
def knowledge(tmp_path):
    (tmp_path / "returns.md").write_text("# Returns\n\n## Window\n\n14 days.\n\n## Refunds\n\n5 to 7 days.\n")
    (tmp_path / "contact.md").write_text("# Contact\n\n## Email\n\nsupport@example.test\n")
    return tmp_path


@pytest.fixture
def embedder():
    return FakeEmbedder()


def sources(db):
    db.expire_all()
    return sorted(db.scalars(select(Document.source)))


def test_first_run_adds_every_file_in_one_embedding_call(db, knowledge, embedder):
    summary = ingest_knowledge(knowledge, db, embed=embedder)

    assert sorted(summary.added) == ["contact.md", "returns.md"]
    assert summary.chunks_per_file == {"contact.md": 1, "returns.md": 2}
    assert len(embedder.calls) == 1
    assert embedder.calls[0][1] == "document"
    assert len(embedder.calls[0][0]) == 3
    assert db.scalar(select(Chunk).where(Chunk.chunk_index == 0)).embedding_model == settings.embedding_model


def test_unchanged_files_are_skipped(db, knowledge, embedder):
    ingest_knowledge(knowledge, db, embed=embedder)
    embedder.calls.clear()

    summary = ingest_knowledge(knowledge, db, embed=embedder)

    assert sorted(summary.unchanged) == ["contact.md", "returns.md"]
    assert summary.texts_embedded == 0
    assert embedder.calls == []


def test_only_changed_files_are_re_embedded(db, knowledge, embedder):
    ingest_knowledge(knowledge, db, embed=embedder)
    embedder.calls.clear()
    (knowledge / "returns.md").write_text("# Returns\n\n## Window\n\n30 days.\n")

    summary = ingest_knowledge(knowledge, db, embed=embedder)

    assert summary.updated == ["returns.md"]
    assert summary.unchanged == ["contact.md"]
    assert embedder.calls == [(["Returns > Window\n\n30 days."], "document")]
    db.expire_all()
    contents = db.scalars(select(Chunk.content).join(Document).where(Document.source == "returns.md")).all()
    assert contents == ["Returns > Window\n\n30 days."]  # old chunks replaced


def test_deleted_files_are_removed_with_their_chunks(db, knowledge, embedder):
    ingest_knowledge(knowledge, db, embed=embedder)
    (knowledge / "contact.md").unlink()

    summary = ingest_knowledge(knowledge, db, embed=embedder)

    assert summary.removed == ["contact.md"]
    assert sources(db) == ["returns.md"]
    assert db.query(Chunk).count() == 2


def test_failed_embedding_saves_nothing_and_the_next_run_retries(db, knowledge, embedder):
    embedder.fail = True
    with pytest.raises(AIServiceError):
        ingest_knowledge(knowledge, db, embed=embedder)
    assert sources(db) == []

    embedder.fail = False
    summary = ingest_knowledge(knowledge, db, embed=embedder)

    assert sorted(summary.added) == ["contact.md", "returns.md"]


def test_reembed_all_re_embeds_unchanged_files(db, knowledge, embedder):
    ingest_knowledge(knowledge, db, embed=embedder)
    embedder.calls.clear()

    summary = ingest_knowledge(knowledge, db, embed=embedder, reembed_all=True)

    assert sorted(summary.updated) == ["contact.md", "returns.md"]
    assert len(embedder.calls) == 1 and len(embedder.calls[0][0]) == 3


def test_chunks_from_another_embedding_model_are_re_embedded(db, knowledge, embedder):
    ingest_knowledge(knowledge, db, embed=embedder)
    db.query(Chunk).update({Chunk.embedding_model: "some-old-model"})
    db.commit()

    summary = ingest_knowledge(knowledge, db, embed=embedder)

    assert sorted(summary.updated) == ["contact.md", "returns.md"]
