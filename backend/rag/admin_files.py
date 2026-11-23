"""Files the admin uploads to add knowledge: notices, brochures, fee lists (PDF, Word .docx, text / Markdown).

The text is taken out with its structure (PDF pages, Word headings, paragraphs and tables, Markdown
headings) and becomes a document that goes through the same steps as a website page and the admin's
answers: the structure-aware chunker, the embedding model, Qdrant and the BM25 index. Answers cite it
as "Document from the admission office", linking to the file itself (/api/files/<id>).

Stored in DATA_DIR/admin/files/ with the list in DATA_DIR/admin/files.json.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from rag.models import Block, PageDocument

DOC_PREFIX = "admin-file-"  # starts with "admin-": merged, re-chunked and indexed with the admin's answers
TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}
MAX_BYTES = 20 * 1024 * 1024


class BadFile(ValueError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_name(name: str) -> str:
    name = Path(str(name or "")).name.strip()
    name = re.sub(r"[^\w .()\-]+", "_", name, flags=re.UNICODE)[:120].strip(" .")
    return name or "file"


# ------------------------------------------------------------------ reading the files
def _pdf_blocks(data: bytes, title: str) -> list[Block]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise BadFile("This PDF could not be read. Is it damaged or password protected?") from exc
    blocks: list[Block] = []
    for number, text in enumerate(pages, 1):
        heading = f"{title} - page {number}" if len(pages) > 1 else title
        for para in re.split(r"\n\s*\n", text):
            para = re.sub(r"[ \t]+", " ", para).strip()
            if para and re.search(r"\w", para):
                blocks.append(Block(type="text", text=para, heading_path=[heading]))
    return blocks


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_blocks(data: bytes, title: str) -> list[Block]:
    """Word: headings (Heading 1-6 / Title styles), paragraphs and tables, in document order."""
    from lxml import etree

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
        body = etree.fromstring(xml).find(f"{_W}body")
    except Exception as exc:
        raise BadFile("This Word file could not be read. Please save it as .docx (not .doc) and try again.") from exc

    def text_of(node) -> str:
        parts = []
        for el in node.iter():
            if el.tag == f"{_W}t" and el.text:
                parts.append(el.text)
            elif el.tag in (f"{_W}tab",):
                parts.append(" ")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        return re.sub(r"[ \t]+", " ", "".join(parts)).strip()

    blocks: list[Block] = []
    path: list[str] = []
    for child in body if body is not None else []:
        if child.tag == f"{_W}p":
            text = text_of(child)
            if not text:
                continue
            style = child.find(f"{_W}pPr/{_W}pStyle")
            name = (style.get(f"{_W}val") if style is not None else "") or ""
            level = 1 if name.lower() == "title" else int(m.group(1)) if (m := re.match(r"(?i)heading\s*(\d)", name)) else 0
            if level:
                path = path[: level - 1] + [text]
                blocks.append(Block(type="heading", text=text, level=level, heading_path=list(path)))
            else:
                blocks.append(Block(type="text", text=text, heading_path=list(path) or [title]))
        elif child.tag == f"{_W}tbl":
            rows = []
            for row in child.iter(f"{_W}tr"):
                cells = [text_of(cell) for cell in row.iter(f"{_W}tc")]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append(Block(type="table", text="\n".join(rows), rows=rows, table_header=rows[0],
                                    heading_path=list(path) or [title]))
    return blocks


def _text_blocks(data: bytes, title: str, markdown: bool) -> list[Block]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    blocks: list[Block] = []
    path: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        heading = re.match(r"^(#{1,6})\s+(.+)$", para) if markdown else None
        if heading and "\n" not in para:
            level = len(heading.group(1))
            path = path[: level - 1] + [heading.group(2).strip()]
            blocks.append(Block(type="heading", text=heading.group(2).strip(), level=level, heading_path=list(path)))
        elif para and re.search(r"\w", para):
            blocks.append(Block(type="text", text=para, heading_path=list(path) or [title]))
    return blocks


def read_blocks(data: bytes, filename: str) -> list[Block]:
    """The file's text as blocks; BadFile with a message for people when it cannot be used."""
    suffix = Path(filename).suffix.lower()
    if suffix not in TYPES:
        raise BadFile("Please upload a PDF, Word (.docx), text (.txt) or Markdown (.md) file.")
    if not data:
        raise BadFile("The file is empty.")
    if len(data) > MAX_BYTES:
        raise BadFile(f"The file is too large (the limit is {MAX_BYTES // (1024 * 1024)} MB).")
    title = Path(safe_name(filename)).stem.replace("_", " ").strip() or "Document"
    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise BadFile("This is not a PDF file.")
        blocks = _pdf_blocks(data, title)
    elif suffix == ".docx":
        if not data.startswith(b"PK"):
            raise BadFile("This is not a Word .docx file. Please save it as .docx and try again.")
        blocks = _docx_blocks(data, title)
    else:
        blocks = _text_blocks(data, title, markdown=suffix == ".md")
    if not any(b.type != "heading" for b in blocks):
        raise BadFile("No text was found in this file. If it is a scanned PDF (a photo of paper), please upload "
                      "a version with selectable text, or type the information as an answer instead.")
    return blocks


# ------------------------------------------------------------------ the store
class FileStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.files_dir = self.folder / "files"
        self.index = self.folder / "files.json"
        self._lock = threading.Lock()

    def all(self) -> list[dict]:
        try:
            data = json.loads(self.index.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write(self, entries: list[dict]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.index.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index)

    def get(self, file_id: str) -> dict | None:
        return next((e for e in self.all() if e["id"] == file_id), None)

    def path_of(self, entry: dict) -> Path:
        return self.files_dir / entry["stored"]

    def add(self, filename: str, data: bytes) -> dict:
        blocks = read_blocks(data, filename)  # check it before keeping it
        name = safe_name(filename)
        file_id = secrets.token_hex(6)
        entry = {"id": file_id, "name": name, "stored": f"{file_id}{Path(name).suffix.lower()}",
                 "type": Path(name).suffix.lower().lstrip("."), "size": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "uploaded_at": _now(),
                 "words": sum(len(b.text.split()) for b in blocks)}
        with self._lock:
            entries = self.all()
            if any(e.get("sha256") == entry["sha256"] for e in entries):
                raise BadFile("This file has already been uploaded.")
            self.files_dir.mkdir(parents=True, exist_ok=True)
            self.path_of(entry).write_bytes(data)
            entries.append(entry)
            self._write(entries)
        return entry

    def delete(self, file_id: str) -> bool:
        with self._lock:
            entries = self.all()
            entry = next((e for e in entries if e["id"] == file_id), None)
            if entry is None:
                return False
            self.path_of(entry).unlink(missing_ok=True)
            self._write([e for e in entries if e["id"] != file_id])
            return True


def file_documents(settings) -> list[PageDocument]:
    """The uploaded files as documents for the chunker (read again each time: the file is the source)."""
    store = FileStore(settings.data_dir / "admin")
    docs = []
    for entry in store.all():
        try:
            data = store.path_of(entry).read_bytes()
            blocks = read_blocks(data, entry["name"])
        except (OSError, BadFile):
            continue
        title = Path(entry["name"]).stem.replace("_", " ").strip()
        docs.append(PageDocument(doc_id=DOC_PREFIX + entry["id"], url=f"/api/files/{entry['id']}", title=title,
                                 blocks=blocks, content_hash=entry["sha256"], fetched_at=entry["uploaded_at"],
                                 content_type=TYPES[Path(entry["name"]).suffix.lower()].split(";")[0], kind="document"))
    return docs
