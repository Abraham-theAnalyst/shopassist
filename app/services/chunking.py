"""Split a Markdown knowledge file into chunks for embedding.

Each heading starts a new section. Long sections are split between
paragraphs. Every chunk starts with its document title and section
heading, so a chunk like "14 days from delivery" still says it is about
returns.
"""

import re
from dataclasses import dataclass

# Roughly 150 to 250 words. Well under the embedding model's 32,768-token
# limit, and small enough that each chunk covers a single topic.
MAX_CHUNK_CHARS = 1200

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    index: int
    content: str


def title_from(markdown: str, fallback: str) -> str:
    """The first top-level heading ("# Title"), or the fallback if there is none."""
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2)
    return fallback


def _sections(markdown: str) -> list[tuple[str | None, str]]:
    """(heading, body) pairs. Text before the first subheading has heading None."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            continue  # the document title, used as the prefix instead
        if match:
            sections.append((match.group(2), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def _paragraphs(body: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    pieces = []
    for paragraph in paragraphs:
        if len(paragraph) <= MAX_CHUNK_CHARS:
            pieces.append(paragraph)
        else:
            # A very long paragraph is split between sentences
            pieces.extend(s for s in _SENTENCE_END.split(paragraph) if s)
    return pieces


def chunk_markdown(markdown: str, title: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, body in _sections(markdown):
        if not body:
            continue
        prefix = f"{title} > {heading}" if heading else title
        current: list[str] = []
        for piece in _paragraphs(body):
            if current and len("\n\n".join(current + [piece])) > MAX_CHUNK_CHARS:
                chunks.append(Chunk(len(chunks), f"{prefix}\n\n" + "\n\n".join(current)))
                current = []
            current.append(piece)
        if current:
            chunks.append(Chunk(len(chunks), f"{prefix}\n\n" + "\n\n".join(current)))
    return chunks
