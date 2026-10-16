"""Find the knowledge base chunks most relevant to a customer's message."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Chunk, Document
from app.services.ai import AIServiceError, embed_texts

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    source: str
    content: str
    # Cosine similarity to the search text; None for always included chunks
    similarity: float | None

    @property
    def label(self) -> str:
        """The chunk's first line, e.g. "Returns and Exchanges > Sale items"."""
        return self.content.split("\n", 1)[0]


def build_search_text(user_messages: list[str]) -> str:
    """The latest customer message, plus the one before it if there is one.

    Including the previous message keeps follow ups like "And to Abuja?"
    on topic. user_messages is oldest first.
    """
    return "\n".join(user_messages[-2:])


def search_by_vector(db: Session, vector: Sequence[float], limit: int | None) -> list[RetrievedChunk]:
    """Chunks ordered from most to least similar to vector (no threshold)."""
    distance = Chunk.embedding.cosine_distance(vector)
    query = (
        select(Document.source, Chunk.content, (1 - distance).label("similarity"))
        .join(Document)
        # Chunks embedded by another model can't be compared with this query
        .where(Chunk.embedding_model == settings.embedding_model)
        .order_by(distance)
    )
    if limit is not None:
        query = query.limit(limit)
    return [RetrievedChunk(source, content, float(sim)) for source, content, sim in db.execute(query)]


def relevant_chunks(db: Session, vector: Sequence[float]) -> list[RetrievedChunk]:
    """At most RAG_TOP_K chunks, each at least RAG_MIN_SIMILARITY."""
    closest = search_by_vector(db, vector, settings.rag_top_k)
    chunks = [c for c in closest if c.similarity >= settings.rag_min_similarity]
    # Labels and scores only, never the customer's text
    if chunks:
        logger.info(
            "Retrieved %d chunk(s): %s",
            len(chunks), "; ".join(f"{c.label} ({c.similarity:.3f})" for c in chunks),
        )
    else:
        best = f"{closest[0].similarity:.3f}" if closest else "none"
        logger.info("No chunks above RAG_MIN_SIMILARITY=%.2f (best %s)", settings.rag_min_similarity, best)
    return chunks


def retrieve(db: Session, search_text: str, embed=embed_texts) -> list[RetrievedChunk]:
    """Embed search_text as a query and return the relevant chunks.

    Raises AIServiceError if embedding fails.
    """
    [vector] = embed([search_text], "query")
    return relevant_chunks(db, vector)


def always_included_chunks(db: Session, exclude: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Every chunk of the documents named in RAG_ALWAYS_INCLUDE, minus any in exclude.

    Lets every reply include e.g. the store's contact details, whatever the
    question was.
    """
    sources = [f"{name}.md" for name in settings.rag_always_include_list]
    if not sources:
        return []
    already = {(c.source, c.content) for c in exclude}
    rows = db.execute(
        select(Document.source, Chunk.content)
        .join(Document)
        .where(Document.source.in_(sources), Chunk.embedding_model == settings.embedding_model)
        .order_by(Document.source, Chunk.chunk_index)
    ).all()
    chunks = [RetrievedChunk(s, c, None) for s, c in rows if (s, c) not in already]
    if chunks:
        logger.info("Always included %d chunk(s): %s", len(chunks), "; ".join(c.label for c in chunks))
    return chunks


def find_store_information(db: Session, search_text: str, embed=embed_texts) -> list[RetrievedChunk]:
    """Everything that goes in the prompt's store information section.

    The relevant chunks first, then the always included ones. If the search
    fails, logs a warning and returns only the always included chunks, so
    the customer still gets a reply (and the support contact details).
    """
    chunks: list[RetrievedChunk] = []
    try:
        chunks = retrieve(db, search_text, embed)
    except AIServiceError:
        logger.warning("Knowledge base search skipped: embedding failed")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Knowledge base search skipped: database error (%s)", type(exc).__name__)
    try:
        return chunks + always_included_chunks(db, exclude=chunks)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Always included documents skipped: database error (%s)", type(exc).__name__)
        return chunks
