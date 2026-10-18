import io

import httpx
import pytest
from PIL import Image

from rag.demo.site import _poster
from rag.images.downloader import ImageDownloader, average_hash, hamming, validate_image_bytes
from rag.images.image_chunker import build_image_chunk, build_image_text, extract_keywords
from rag.images.ocr import NoOcr, RapidOcrEngine, get_ocr_engine
from rag.images.stage import image_file_path
from rag.models import ImageRecord


def png_bytes(size=(200, 150), color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def make_downloader(tmp_path, routes: dict[str, httpx.Response], max_bytes=1_000_000):
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ImageDownloader(tmp_path, max_bytes=max_bytes, min_dimension=80, client=client, retries=0)


def test_validate_rejects_garbage_and_small_images():
    result, img = validate_image_bytes(b"<html>not an image</html>", 80)
    assert result.status == "invalid" and img is None
    result, img = validate_image_bytes(png_bytes((20, 20)), 80)
    assert result.status == "skipped_small"
    result, img = validate_image_bytes(png_bytes(), 80)
    assert result.status == "ok" and result.mime_type == "image/png" and (result.width, result.height) == (200, 150)


def test_downloader_stores_by_hash_and_handles_errors(tmp_path):
    data = png_bytes()
    dl = make_downloader(tmp_path, {
        "https://c.example/ok.png": httpx.Response(200, content=data),
        "https://c.example/big.png": httpx.Response(200, content=data + b"\0" * 2_000_000),
        "https://c.example/../../etc/passwd.png": httpx.Response(200, content=data),
    })
    ok = dl.download("https://c.example/ok.png")
    assert ok.status == "ok" and ok.local_path.endswith(".png") and ok.local_path.startswith(ok.sha256[:2])
    assert (tmp_path / ok.local_path).read_bytes() == data
    assert dl.download("https://c.example/missing.png").status == "http_error"
    assert dl.download("https://c.example/big.png").status == "too_large"
    # remote names never decide the local path
    evil = dl.download("https://c.example/../../etc/passwd.png")
    assert ".." not in evil.local_path


def test_image_file_path_blocks_traversal(settings, tmp_path):
    settings.ensure_dirs()
    (settings.images_dir / "ab").mkdir()
    (settings.images_dir / "ab" / "x.png").write_bytes(b"x")
    assert image_file_path(settings, "ab/x.png") is not None
    assert image_file_path(settings, "../status.json") is None
    assert image_file_path(settings, "/etc/passwd") is None
    assert image_file_path(settings, "") is None


def test_average_hash_detects_resized_copies():
    base = Image.new("RGB", (400, 300), "white")
    for x in range(0, 400, 40):
        base.paste((0, 0, 0), (x, 0, x + 20, 300))
    small = base.resize((200, 150))
    other = Image.new("RGB", (400, 300), "white")
    other.paste((0, 0, 0), (0, 0, 400, 150))
    assert hamming(average_hash(base), average_hash(small)) <= 3
    assert hamming(average_hash(base), average_hash(other)) > 10


def test_rapidocr_reads_poster_text(tmp_path):
    path = tmp_path / "poster.png"
    _poster(path)
    engine = get_ocr_engine("rapidocr")
    if not isinstance(engine, RapidOcrEngine):
        pytest.skip("rapidocr not installed")
    result = engine.read(path)
    text = result.text.upper()
    # OCR is imperfect (e.g. "DIT" may read as "DLT"); assert on robustly read lines
    assert "ADMISSIONS" in text and "ROBOTICS ENGINEERING" in text and "0420" in text and "HELPLINE" in text
    assert 0.6 <= result.confidence <= 1.0
    # lines are ordered top to bottom
    assert text.index("ADMISSIONS") < text.index("ROBOTICS")


def test_unknown_ocr_engine_falls_back_to_none():
    assert isinstance(get_ocr_engine("none"), NoOcr)


def test_image_chunk_text_labels_provenance_and_keywords_ignore_ai_text():
    record = ImageRecord(image_id="i1", url="https://c.example/img/hostel-block.jpg", alt="Boys hostel", caption="Hostel A",
                         filename="hostel-block.jpg", page_title="Facilities", heading="Hostel", heading_path=["Facilities", "Hostel"],
                         ocr_text="WELCOME", description="A tall building with blue windows", description_model="m")
    text = build_image_text(record)
    assert "Alt text: Boys hostel" in text
    assert "Text in image (OCR): WELCOME" in text
    assert "AI-generated description: A tall building" in text
    keywords = extract_keywords(record)
    assert "hostel" in keywords and "windows" not in keywords
    chunk = build_image_chunk(record)
    assert chunk.chunk_id == "i1" and chunk.metadata["description_model"] == "m"


def test_image_stage_on_demo_site(pipeline):
    from rag.models import ImageChunk
    from rag.utils import read_jsonl

    records = {r.url.rsplit("/", 1)[-1]: r for r in read_jsonl(pipeline.settings.images_file, ImageRecord)}
    assert records["missing-photo.jpg"].status == "http_error"
    assert records["library-reading-hall-copy.jpg"].status == "duplicate"
    assert records["library-reading-hall-copy.jpg"].duplicate_of == records["library.jpg"].image_id
    assert "icon-arrow.png" not in records  # filtered by width/height attributes
    poster = records["admission-notice.png"]
    assert poster.status == "ok" and poster.alt == "" and "ADMISSIONS" in poster.ocr_text.upper()
    assert poster.width == 900 and poster.height == 1200 and poster.mime_type == "image/png"
    lab = records["computer-lab.jpg"]
    assert lab.heading == "Laboratories" and lab.caption == "Programming laboratory"
    assert lab.source_page.endswith("/departments/computer-science.html")
    chunks = list(read_jsonl(pipeline.settings.image_chunks_file, ImageChunk))
    assert {c.image_id for c in chunks} == {r.image_id for r in records.values() if r.status == "ok"}


def test_logo_on_every_page_marked_boilerplate(tmp_path):
    from rag.images.stage import run_image_stage
    from rag.models import ImageRef, PageDocument
    from rag.utils import read_jsonl, write_jsonl
    from tests.conftest import make_settings

    settings = make_settings(tmp_path / "data", crawl_allowed_domains=["c.example"])
    settings.ensure_dirs()
    docs = [PageDocument(doc_id=str(i), url=f"https://c.example/{i}", title=str(i), content_hash=str(i),
                         images=[ImageRef(url="https://c.example/logo.png", source_page=f"https://c.example/{i}")])
            for i in range(4)]
    write_jsonl(settings.documents_file, docs)
    dl = make_downloader(settings.images_dir, {"https://c.example/logo.png": httpx.Response(200, content=png_bytes())})
    run_image_stage(settings, downloader=dl)
    [record] = list(read_jsonl(settings.images_file, ImageRecord))
    assert record.status == "boilerplate"


def test_interrupted_image_downloads_resume_from_journal(tmp_path):
    from rag.images.stage import run_image_stage
    from rag.models import ImageRef, PageDocument
    from rag.utils import write_jsonl
    from tests.conftest import make_settings

    settings = make_settings(tmp_path / "data", crawl_allowed_domains=["c.example"])
    settings.ensure_dirs()
    refs = [ImageRef(url=f"https://c.example/{i}.png", alt=f"photo {i}", source_page="https://c.example/p") for i in range(3)]
    write_jsonl(settings.documents_file, [PageDocument(doc_id="p", url="https://c.example/p", title="P", content_hash="h", images=refs)])
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=png_bytes(color=["red", "green", "blue"][int(str(request.url)[-5])]))

    def downloader():
        return ImageDownloader(settings.images_dir, 1_000_000, 80, client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0)

    run_image_stage(settings, downloader=downloader())
    assert len(calls) == 3
    settings.images_file.unlink()  # simulate a run killed before records were written
    run_image_stage(settings, downloader=downloader())
    assert len(calls) == 3  # nothing downloaded twice
