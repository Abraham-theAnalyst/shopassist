"""Load knowledge/*.md into the documents and chunks tables."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Chunk, Document
from app.services.ai import EmbeddingMode, embed_texts
from app.services.chunking import chunk_markdown, title_from

logger = logging.getLogger(__name__)

EmbedFunction = Callable[[list[str], EmbeddingMode], list[list[float]]]


@dataclass
class IngestionSummary:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    chunks_per_file: dict[str, int] = field(default_factory=dict)
    texts_embedded: int = 0


@dataclass
class _PendingDocument:
    source: str
    title: str
    content_hash: str
    chunk_texts: list[str]
    existing: Document | None


def _needs_embedding(document: Document, content_hash: str, reembed_all: bool, db: Session) -> bool:
    if reembed_all or document.content_hash != content_hash:
        return True
    # Chunks from a different embedding model can't be compared with new queries
    other_model = db.scalar(
        select(Chunk.id).where(
            Chunk.document_id == document.id, Chunk.embedding_model != settings.embedding_model
        ).limit(1)
    )
    return other_model is not None


def ingest_knowledge(
    knowledge_dir: Path,
    db: Session,
    embed: EmbedFunction = embed_texts,
    reembed_all: bool = False,
) -> IngestionSummary:
    """Sync the database with the Markdown files in knowledge_dir.

    All new embeddings are requested first, in as few requests as possible.
    Then each document is saved in its own transaction. If embedding fails,
    nothing is saved, so the next run tries those files again.
    """
    summary = IngestionSummary()
    files = sorted(knowledge_dir.glob("*.md"))
    existing = {d.source: d for d in db.scalars(select(Document))}

    pending: list[_PendingDocument] = []
    for path in files:
        raw = path.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        document = existing.get(path.name)
        if document and not _needs_embedding(document, content_hash, reembed_all, db):
            summary.unchanged.append(path.name)
            summary.chunks_per_file[path.name] = len(document.chunks)
            continue
        markdown = raw.decode("utf-8")
        title = title_from(markdown, fallback=path.stem.replace("-", " ").capitalize())
        chunk_texts = [c.content for c in chunk_markdown(markdown, title)]
        pending.append(_PendingDocument(path.name, title, content_hash, chunk_texts, document))

    # One embedding call for every new or changed chunk (batched inside embed_texts)
    all_texts = [text for doc in pending for text in doc.chunk_texts]
    vectors = embed(all_texts, "document") if all_texts else []
    summary.texts_embedded = len(all_texts)

    position = 0
    for doc in pending:
        doc_vectors = vectors[position : position + len(doc.chunk_texts)]
        position += len(doc.chunk_texts)
        document = doc.existing or Document(source=doc.source)
        document.title = doc.title
        document.content_hash = doc.content_hash
        if doc.existing:
            db.execute(delete(Chunk).where(Chunk.document_id == doc.existing.id))
        else:
            db.add(document)
        db.flush()
        db.add_all(
            Chunk(
                document_id=document.id,
                chunk_index=i,
                content=text,
                embedding=vector,
                embedding_model=settings.embedding_model,
            )
            for i, (text, vector) in enumerate(zip(doc.chunk_texts, doc_vectors))
        )
        db.commit()  # one transaction per document
        db.expire(document)
        (summary.updated if doc.existing else summary.added).append(doc.source)
        summary.chunks_per_file[doc.source] = len(doc.chunk_texts)

    file_names = {path.name for path in files}
    for source, document in existing.items():
        if source not in file_names:
            db.delete(document)  # its chunks are deleted with it
            db.commit()
            summary.removed.append(source)

    return summary
