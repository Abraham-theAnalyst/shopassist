"""Find the knowledge base chunks most relevant to a customer's message."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Chunk, Document
from app.services.ai import embed_texts

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    source: str
    content: str
    similarity: float

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


def retrieve(db: Session, search_text: str, embed=embed_texts) -> list[RetrievedChunk]:
    """The closest chunks by cosine similarity: at most RAG_TOP_K, each at
    least RAG_MIN_SIMILARITY. Raises AIServiceError if embedding fails.
    """
    [query_vector] = embed([search_text], "query")
    distance = Chunk.embedding.cosine_distance(query_vector)
    rows = db.execute(
        select(Document.source, Chunk.content, (1 - distance).label("similarity"))
        .join(Document)
        # Chunks embedded by another model can't be compared with this query
        .where(Chunk.embedding_model == settings.embedding_model)
        .order_by(distance)
        .limit(settings.rag_top_k)
    ).all()
    closest = [RetrievedChunk(source, content, float(similarity)) for source, content, similarity in rows]
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
