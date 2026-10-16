from app.services.chunking import MAX_CHUNK_CHARS, chunk_markdown, title_from

DOC = """# Returns and Exchanges

Intro text before any section.

## Refunds

Refunds go to your original payment method.

## Empty section

## Sale items

Sale items cannot be refunded.

They can only be exchanged for a different size.
"""


def test_title_comes_from_the_top_heading():
    assert title_from(DOC, fallback="returns") == "Returns and Exchanges"


def test_title_falls_back_when_there_is_no_top_heading():
    assert title_from("## Only a subheading\n\nText", fallback="Sizing") == "Sizing"


def test_one_chunk_per_section_prefixed_with_title_and_heading():
    chunks = chunk_markdown(DOC, "Returns and Exchanges")

    assert [c.content.split("\n")[0] for c in chunks] == [
        "Returns and Exchanges",
        "Returns and Exchanges > Refunds",
        "Returns and Exchanges > Sale items",
    ]
    assert [c.index for c in chunks] == [0, 1, 2]


def test_paragraphs_of_a_section_stay_together_when_short():
    sale = chunk_markdown(DOC, "Returns and Exchanges")[2].content

    assert "cannot be refunded" in sale
    assert "exchanged for a different size" in sale


def test_empty_sections_produce_no_chunks():
    assert not any("Empty section" in c.content for c in chunk_markdown(DOC, "T"))


def test_long_sections_are_split_between_paragraphs_and_keep_the_prefix():
    paragraphs = [f"Paragraph {i}. " + "word " * 60 for i in range(10)]
    markdown = "# Guide\n\n## Long section\n\n" + "\n\n".join(paragraphs)

    chunks = chunk_markdown(markdown, "Guide")

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.content.startswith("Guide > Long section\n\n")
        assert len(chunk.content) <= MAX_CHUNK_CHARS + len("Guide > Long section\n\n")
    # Every paragraph is kept, in order
    joined = " ".join(c.content for c in chunks)
    assert [joined.index(f"Paragraph {i}.") for i in range(10)] == sorted(
        joined.index(f"Paragraph {i}.") for i in range(10)
    )
