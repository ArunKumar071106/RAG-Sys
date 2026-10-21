import pytest

from rag.chunking.stage import dedupe_chunks
from rag.chunking.text_chunker import StructureAwareChunker, split_sentences
from rag.chunking.tokens import count_tokens
from rag.models import Block, PageDocument


def doc(blocks, url="https://c.example/p", title="Page"):
    return PageDocument(doc_id="d1", url=url, title=title, blocks=blocks, content_hash="x")


def h(text, level, path):
    return Block(type="heading", text=text, level=level, heading_path=path)


def t(text, path):
    return Block(type="text", text=text, heading_path=path)


def test_split_sentences_respects_abbreviations():
    text = "Dr. A. Kumar is the HOD. He holds a Ph.D. in AI. The B.E. course started in 2013! Apply now."
    assert split_sentences(text) == [
        "Dr. A. Kumar is the HOD.", "He holds a Ph.D. in AI.", "The B.E. course started in 2013!", "Apply now.",
    ]


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ValueError):
        StructureAwareChunker(chunk_size=100, overlap=100)


def test_small_sections_under_same_top_heading_are_merged_with_headings():
    blocks = [h("About", 1, ["About"]), t("Founded in 2013.", ["About"]),
              h("Vision", 2, ["About", "Vision"]), t("Excellence in education.", ["About", "Vision"]),
              h("Contact", 1, ["Contact"]), t("Phone 123.", ["Contact"])]
    chunks = StructureAwareChunker(chunk_size=200, overlap=20).chunk_document(doc(blocks))
    assert len(chunks) == 2
    assert "## About" in chunks[0].text and "### Vision" in chunks[0].text and "Excellence" in chunks[0].text
    assert chunks[0].heading_path == ["About"]
    assert chunks[1].heading_path == ["Contact"]


def test_large_section_split_respects_size_and_overlaps():
    sentences = [f"Fact number {i} about the central library collection." for i in range(80)]
    blocks = [h("Library", 2, ["Facilities", "Library"])] + [t(" ".join(sentences[i:i + 4]), ["Facilities", "Library"]) for i in range(0, 80, 4)]
    chunker = StructureAwareChunker(chunk_size=120, overlap=25, min_tokens=10)
    chunks = chunker.chunk_document(doc(blocks))
    assert len(chunks) > 3
    for c in chunks:
        assert c.token_count <= 120 + 25 + 10  # budget + overlap + heading line slack
        assert c.text.startswith("### Library")
        assert c.heading_path == ["Facilities", "Library"]
    # consecutive chunks share overlapping sentences
    first_tail = chunks[0].text.splitlines()[-1].split(". ")[-1]
    assert first_tail.rstrip(".") in chunks[1].text
    # all facts are covered
    joined = " ".join(c.text for c in chunks)
    assert all(f"Fact number {i} " in joined for i in range(80))


def test_tables_split_on_rows_and_repeat_header():
    rows = [f"Company: Recruiter {i} | Offers: {i}" for i in range(60)]
    table = Block(type="table", text="\n".join(rows), heading_path=["Placements"], rows=rows, table_header="Company | Offers")
    chunks = StructureAwareChunker(chunk_size=100, overlap=20, min_tokens=5).chunk_document(doc([h("Placements", 1, ["Placements"]), table]))
    assert len(chunks) > 2
    seen = []
    for c in chunks:
        lines = [line for line in c.text.splitlines() if line.startswith("Company:")]
        assert "Company | Offers" in c.text
        seen.extend(lines)
    assert seen == rows  # every row exactly once, never cut, never overlapped


def test_chunk_metadata_and_title_not_repeated_in_path():
    blocks = [h("Page", 1, ["Page"]), t("Body text here.", ["Page"])]
    [chunk] = StructureAwareChunker().chunk_document(doc(blocks), duplicate_urls=["https://c.example/p2"])
    assert chunk.page_title == "Page" and chunk.heading_path == []
    assert chunk.url == "https://c.example/p" and chunk.doc_id == "d1"
    assert chunk.token_count == count_tokens(chunk.text)
    assert chunk.duplicate_urls == ["https://c.example/p2"]
    assert chunk.embedding_text().startswith("Page\n")


def test_dedupe_chunks_keeps_first_and_records_other_urls():
    blocks = [t("Shared paragraph about scholarships.", [])]
    a = StructureAwareChunker().chunk_document(doc(blocks, url="https://c.example/a"))
    b = StructureAwareChunker().chunk_document(doc(blocks, url="https://c.example/b"))
    kept, removed = dedupe_chunks(a + b)
    assert removed == 1 and len(kept) == 1
    assert kept[0].duplicate_urls == ["https://c.example/b"]


def test_demo_pipeline_chunks_have_required_fields(pipeline):
    from rag.models import TextChunk
    from rag.utils import read_jsonl

    chunks = list(read_jsonl(pipeline.settings.chunks_file, TextChunk))
    assert chunks
    for c in chunks:
        assert c.chunk_id and c.doc_id and c.url.startswith("http") and c.page_title and c.content_hash
        assert c.token_count <= pipeline.settings.chunk_size_tokens + pipeline.settings.chunk_overlap_tokens + 20


@pytest.mark.parametrize("n_long", [1, 3])
def test_tiny_trailing_piece_is_folded_into_previous(n_long):
    """Regression: the fold indexed the list after pop(), which crashed with two pieces and,
    with more, silently overwrote a piece (found on a real department page)."""
    chunker = StructureAwareChunker(chunk_size=60, overlap=10, min_tokens=20)
    budget = 60 - count_tokens("## Lab")

    def sentence(i):  # one sentence that fits a piece on its own, but not together with another
        words = [f"Fact{i}"]
        while count_tokens(" ".join(words) + ".") < budget - 2:
            words.append("equipment")
        return " ".join(words) + "."

    longs = [sentence(i) for i in range(n_long)]
    blocks = [h("Lab", 1, ["Lab"])] + [t(x, ["Lab"]) for x in longs] + [t("Short end.", ["Lab"])]
    chunks = chunker.chunk_document(doc(blocks))
    joined = "\n".join(c.text for c in chunks)
    assert len(chunks) == n_long
    assert chunks[-1].text.endswith("Short end.") and joined.count("Short end.") == 1
    for i in range(n_long):
        assert joined.count(f"Fact{i} ") == 1  # every piece kept exactly once


def test_separate_sections_stay_separate_and_only_tiny_siblings_merge():
    body = "Candidates must pass the qualifying examination with the required marks in the main subjects. " * 3
    blocks = [h("Admission", 2, ["Admission"]), t("Welcome.", ["Admission"]),
              h("Management Quota", 3, ["Admission", "Management Quota"]), t(body, ["Admission", "Management Quota"]),
              h("Government Quota", 3, ["Admission", "Government Quota"]), t(body, ["Admission", "Government Quota"]),
              h("Reservation Policy", 3, ["Admission", "Reservation Policy"]), t("As per rules.", ["Admission", "Reservation Policy"]),
              h("Retention Policy", 3, ["Admission", "Retention Policy"]), t("As per UGC.", ["Admission", "Retention Policy"])]
    chunks = StructureAwareChunker(chunk_size=650, overlap=50).chunk_document(doc(blocks, title="Admission"))
    paths = [c.heading_path for c in chunks]
    # two topics under one page heading are two chunks, not one 650-token mix
    assert ["Management Quota"] in paths and ["Government Quota"] in paths
    # the page intro is not merged into the first tab
    assert not any("Welcome." in c.text and "Management Quota" in c.text for c in chunks)
    # two one-line sections share a chunk; both headings stay in its text
    tiny = [c for c in chunks if "As per rules." in c.text][0]
    assert "As per UGC." in tiny.text and "Reservation Policy" in tiny.text and "Retention Policy" in tiny.text
