from rag.models import TextChunk
from rag.utils import clean_text, is_allowed_host, normalize_url, read_jsonl, write_jsonl


def test_normalize_url_strips_fragments_tracking_and_trailing_slash():
    assert normalize_url("HTTPS://Example.ac.in/About/?utm_source=x&b=2&a=1#team") == "https://example.ac.in/About/?a=1&b=2"
    assert normalize_url("../admissions/", "https://example.ac.in/about/us") == "https://example.ac.in/admissions/"
    assert normalize_url("https://example.ac.in") == "https://example.ac.in/"
    assert normalize_url("http://example.ac.in:80//a//b") == "http://example.ac.in/a/b"


def test_allowed_host_matches_domain_and_subdomains_only():
    allowed = ["aaaenggcoll.ac.in"]
    assert is_allowed_host("https://aaaenggcoll.ac.in/x", allowed)
    assert is_allowed_host("https://www.aaaenggcoll.ac.in/x", allowed)
    assert not is_allowed_host("https://evil-aaaenggcoll.ac.in/x", allowed)
    assert not is_allowed_host("https://aaaenggcoll.ac.in.evil.com/x", allowed)


def test_clean_text_normalises_whitespace_but_keeps_paragraphs():
    assert clean_text("  a  b \n\n\n\n c\t ") == "a b\n\nc"


def test_jsonl_roundtrip(tmp_path):
    chunk = TextChunk(chunk_id="c1", doc_id="d", url="u", page_title="t", text="hello", token_count=1, chunk_index=0, content_hash="h")
    path = tmp_path / "x.jsonl"
    assert write_jsonl(path, [chunk, chunk]) == 2
    assert [c.chunk_id for c in read_jsonl(path, TextChunk)] == ["c1", "c1"]
    assert list(read_jsonl(tmp_path / "missing.jsonl", TextChunk)) == []


def test_relative_data_dir_resolves_against_project_root():
    from rag.config import PROJECT_DIR, Settings

    assert Settings(_env_file=None, data_dir="./data").data_dir == (PROJECT_DIR / "data").resolve()
