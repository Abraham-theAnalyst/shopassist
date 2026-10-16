import logging
import re

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings

logger = logging.getLogger(__name__)


def embedding_column_dimensions(engine: Engine) -> int | None:
    """Size of chunks.embedding in the database, e.g. 2048 for halfvec(2048).

    None if the chunks table doesn't exist yet (migrations not applied).
    """
    with engine.connect() as conn:
        column_type = conn.scalar(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = to_regclass('chunks') AND attname = 'embedding'"
            )
        )
    match = re.search(r"\((\d+)\)", column_type or "")
    return int(match.group(1)) if match else None


def check_embedding_dimensions(engine: Engine) -> bool:
    """Log a clear error if EMBEDDING_DIMENSIONS doesn't match the database column.

    Never raises: the app still starts, so the rest of it keeps working.
    """
    try:
        column = embedding_column_dimensions(engine)
    except Exception as exc:
        logger.warning("Could not check the embedding column size: %s", type(exc).__name__)
        return False
    if column is None:
        logger.warning("chunks.embedding not found; have the migrations been applied?")
        return False
    if column != settings.embedding_dimensions:
        logger.error(
            "EMBEDDING_DIMENSIONS=%d does not match the database column chunks.embedding (%d). "
            "Knowledge base search will fail. Fix the setting, or change the column with a "
            "new migration and re-embed with: python -m app.cli.ingest --reembed-all",
            settings.embedding_dimensions, column,
        )
        return False
    return True
