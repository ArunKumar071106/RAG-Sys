"""Files the admin uploads (PDF, Word, text) are read with their structure, chunked and indexed like pages,
cited as their own source; and the admin's "Reset dashboard"."""

import io
import shutil
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from rag.admin_files import BadFile, FileStore, file_documents, read_blocks
from rag.api.app import create_app
from tests.conftest import make_settings

ADMIN = {"Authorization": "Bearer admin-secret"}
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx(*body: str) -> bytes:
    """A minimal Word file: document.xml with the given paragraphs and tables."""
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{"".join(body)}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def para(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


def table(*rows: list[str]) -> str:
    cells = "".join("<w:tr>" + "".join(f"<w:tc>{para(c)}</w:tc>" for c in row) + "</w:tr>" for row in rows)
    return f"<w:tbl>{cells}</w:tbl>"


def pdf(text: str) -> bytes:
    """A one-page PDF with a line of text (enough for pypdf to read)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>stream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


FEES = docx(para("Hostel fees 2026", "Heading1"), para("The hostel fee for first-year students is Rs. 65,000 per year."),
            table(["Item", "Amount"], ["Mess", "Rs. 30,000"], ["Room", "Rs. 35,000"]))


def test_word_files_keep_headings_paragraphs_and_tables():
    blocks = read_blocks(FEES, "Hostel fees.docx")
    assert [b.type for b in blocks] == ["heading", "text", "table"]
    assert blocks[0].text == "Hostel fees 2026" and blocks[1].heading_path == ["Hostel fees 2026"]
    assert blocks[2].rows == ["Item | Amount", "Mess | Rs. 30,000", "Room | Rs. 35,000"]


def test_markdown_text_and_pdf_files_are_read():
    md = read_blocks(b"# Bus routes\n\nBuses leave Sivakasi at 7.30 AM.\n\n## Fees\n\nRs. 12,000 a year.", "routes.md")
    assert [(b.type, b.heading_path) for b in md] == [("heading", ["Bus routes"]), ("text", ["Bus routes"]),
                                                     ("heading", ["Bus routes", "Fees"]), ("text", ["Bus routes", "Fees"])]
    assert read_blocks("Plain notice text.".encode(), "notice.txt")[0].text == "Plain notice text."
    assert "Admission counselling starts on 10 June" in read_blocks(pdf("Admission counselling starts on 10 June"), "notice.pdf")[0].text


@pytest.mark.parametrize("data,name,message", [
    (b"hello", "virus.exe", "Please upload a PDF"),
    (b"", "empty.txt", "empty"),
    (b"not a pdf", "fake.pdf", "not a PDF"),
    (b"not a zip", "old.docx", "save it as .docx"),
    (pdf(""), "scan.pdf", "No text was found"),
])
def test_files_that_cannot_be_used_say_why(data, name, message):
    with pytest.raises(BadFile, match=message):
        read_blocks(data, name)


def test_the_same_file_is_not_added_twice_and_names_are_made_safe(tmp_path):
    store = FileStore(tmp_path)
    entry = store.add("../../etc/Hostel fees?.docx", FEES)
    assert entry["name"] == "Hostel fees_.docx" and store.path_of(entry).parent == tmp_path / "files"
    with pytest.raises(BadFile, match="already been uploaded"):
        store.add("copy.docx", FEES)
    assert store.delete(entry["id"]) and not store.path_of(entry).exists() and store.all() == []


def test_an_uploaded_file_is_indexed_cited_and_removed(pipeline, tmp_path):
    from rag.api.services import Services
    from rag.embeddings.base import HashingEmbedder

    settings = make_settings(tmp_path / "data", admin_token="admin-secret")
    shutil.copytree(pipeline.settings.processed_dir, settings.processed_dir)  # a copy: the shared index stays as it is
    services = Services(settings, embedder=HashingEmbedder(settings.hashing_dim), load_llm=False)

    def wait(client, job):
        for _ in range(100):
            state = client.get(f"/api/admin/jobs/{job}", headers=ADMIN).json()["state"]
            if state in ("finished", "failed"):
                return state
            time.sleep(0.1)

    try:
        with TestClient(create_app(settings, services=services)) as client:
            assert client.post("/api/admin/files?name=fees.docx", content=FEES).status_code == 401  # admin only
            bad = client.post("/api/admin/files?name=scan.pdf", content=pdf(""), headers=ADMIN)
            assert bad.status_code == 422 and "No text was found" in bad.json()["detail"]

            saved = client.post("/api/admin/files?name=Hostel fees.docx", content=FEES, headers=ADMIN).json()
            file_id = saved["file"]["id"]
            assert wait(client, saved["indexing"]) == "finished"
            assert [f["name"] for f in client.get("/api/admin/files", headers=ADMIN).json()] == ["Hostel fees.docx"]
            assert len(file_documents(settings)) == 1

            answer = client.post("/api/chat", json={"message": "What is the hostel fee for first-year students?"}).json()
            assert f"/api/files/{file_id}" in [s["url"] for s in answer["sources"]] and "65,000" in answer["answer"]
            opened = client.get(f"/api/files/{file_id}")
            assert opened.status_code == 200 and opened.content == FEES and "attachment" in opened.headers["content-disposition"]

            removed = client.delete(f"/api/admin/files/{file_id}", headers=ADMIN).json()
            assert wait(client, removed["indexing"]) == "finished"
            assert client.get(f"/api/files/{file_id}").status_code == 404
            after = client.post("/api/chat", json={"message": "What is the hostel fee for first-year students?"}).json()
            assert f"/api/files/{file_id}" not in [s["url"] for s in after["sources"]]
    finally:
        services.close()


def test_reset_dashboard_starts_from_zero_and_keeps_an_archive(pipeline, services, tmp_path):
    settings = pipeline.settings.model_copy(update={"admin_token": "admin-secret", "data_dir": tmp_path / "data"})
    with TestClient(create_app(settings, services=services)) as client:
        for question in ("Is there a hostel?", "zzqx wvvy plorp"):
            client.post("/api/chat", json={"message": question})
        assert client.get("/api/admin/dashboard", headers=ADMIN).json()["totals"]["questions"] == 2
        assert client.post("/api/admin/reset-dashboard").status_code == 401
        archived = client.post("/api/admin/reset-dashboard", headers=ADMIN).json()["archived"]
        board = client.get("/api/admin/dashboard", headers=ADMIN).json()
    assert board["totals"]["questions"] == 0 and board["unanswered"] == [] and board["top_questions"] == []
    kept = settings.data_dir / "feedback" / "archive" / archived
    assert (kept / "questions.jsonl").read_text(encoding="utf-8").count("\n") == 2  # nothing is lost
