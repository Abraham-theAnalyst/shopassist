"""Load the knowledge base files into the database.

Usage:
    python -m app.cli.ingest                 # embed new and changed files only
    python -m app.cli.ingest --reembed-all   # re-embed everything (e.g. after EMBEDDING_MODEL changes)
"""

import argparse
import logging
import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.services.ai import AIServiceError
from app.services.ingestion import ingest_knowledge


def main() -> int:
    parser = argparse.ArgumentParser(description="Load knowledge/*.md into the database.")
    parser.add_argument("--knowledge-dir", type=Path, default=Path("knowledge"))
    parser.add_argument(
        "--reembed-all", action="store_true",
        help="Re-embed every file, even unchanged ones (use after changing EMBEDDING_MODEL)",
    )
    args = parser.parse_args()
    # Shows how many embedding requests were made (never the texts or the key)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not args.knowledge_dir.is_dir():
        print(f"Knowledge folder not found: {args.knowledge_dir}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            summary = ingest_knowledge(args.knowledge_dir, db, reembed_all=args.reembed_all)
        except AIServiceError:
            print("Ingestion failed: the embedding request did not succeed. "
                  "Nothing was changed; run it again later.", file=sys.stderr)
            return 1

    print(
        f"Ingestion complete: {len(summary.added)} added, {len(summary.updated)} updated, "
        f"{len(summary.unchanged)} unchanged, {len(summary.removed)} removed "
        f"({summary.texts_embedded} chunks embedded)"
    )
    for source, count in sorted(summary.chunks_per_file.items()):
        print(f"  {source}: {count} chunks")
    for source in summary.removed:
        print(f"  {source}: removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
