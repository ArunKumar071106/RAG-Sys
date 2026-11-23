"""Answers the admin writes for questions the website does not answer.

Each answer is a small document (the question as its title and heading, the answer as its text)
that goes through the same steps as a website page: the structure-aware chunker, the embedding
model, Qdrant and the keyword (BM25) index. So the next visitor asking the same thing, in any
wording, gets the answer, cited as "Answer from the admission office" (/api/answers/<id>).

Stored in DATA_DIR/admin/answers.json. Saving one updates the index in the background: only the
admin answers are chunked again (chunks.jsonl keeps the website's chunks as they are) and only
what changed is embedded. A full website refresh keeps them too (run_chunking adds them).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from rag.models import Block, PageDocument

DOC_PREFIX = "admin-"
SOURCE_TITLE = "Answer from the admission office"


def question_key(text: str) -> str:
    """The same question in other capitals or punctuation is the same question."""
    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class AnswerStore:
    def __init__(self, folder: Path):
        self.path = Path(folder) / "answers.json"
        self._lock = threading.Lock()

    def all(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, answer_id: str) -> dict | None:
        return next((e for e in self.all() if e["id"] == answer_id), None)

    def save(self, question: str, answer: str, answer_id: str | None = None, resolves: list[str] | None = None) -> dict:
        question, answer = question.strip(), answer.strip()
        if not question or not answer:
            raise ValueError("Both the question and the answer are needed.")
        with self._lock:
            entries = self.all()
            entry = next((e for e in entries if e["id"] == answer_id), None) if answer_id else None
            if answer_id and entry is None:
                raise KeyError(answer_id)
            keys = {question_key(question), *(question_key(r) for r in (resolves or []))} - {""}
            if entry is None:
                entry = {"id": secrets.token_hex(6), "created_at": _now(), "resolves": []}
                entries.append(entry)
            entry.update(question=question, answer=answer, updated_at=_now(),
                         resolves=sorted(set(entry.get("resolves", [])) | keys))
            self._write(entries)
            return entry

    def delete(self, answer_id: str) -> bool:
        with self._lock:
            entries = self.all()
            kept = [e for e in entries if e["id"] != answer_id]
            if len(kept) == len(entries):
                return False
            self._write(kept)
            return True

    def resolved_keys(self) -> set[str]:
        return {key for e in self.all() for key in e.get("resolves", [])}


def answer_documents(settings) -> list[PageDocument]:
    """The admin answers as documents for the chunker."""
    docs = []
    for entry in AnswerStore(settings.data_dir / "admin").all():
        question, answer = entry["question"], entry["answer"]
        # the question is the title (what visitors' wording is matched against); the answer is the text
        blocks = [Block(type="text", text=paragraph) for paragraph in
                  (p.strip() for p in re.split(r"\n\s*\n", answer)) if paragraph]
        digest = hashlib.sha256(f"{question}\n{answer}".encode()).hexdigest()
        docs.append(PageDocument(doc_id=DOC_PREFIX + entry["id"], url=f"/api/answers/{entry['id']}", title=question,
                                 blocks=blocks, content_hash=digest, fetched_at=entry.get("updated_at", ""), kind="answer"))
    return docs


def answer_chunks(settings) -> list:
    """The admin's answers and uploaded files through the same structure-aware chunker as the website's pages."""
    from rag.admin_files import file_documents
    from rag.chunking.text_chunker import StructureAwareChunker

    chunker = StructureAwareChunker(chunk_size=settings.chunk_size_tokens, overlap=settings.chunk_overlap_tokens,
                                    min_tokens=1)  # a one-line answer or a short notice is still worth finding
    docs = answer_documents(settings) + file_documents(settings)
    return [chunk for doc in docs for chunk in chunker.chunk_document(doc)]


def merge_answer_chunks(settings) -> int:
    """Chunk the admin answers again and put them in chunks.jsonl in place of the previous ones
    (the website's chunks stay as they are, so no extracted pages are needed)."""
    from rag.models import TextChunk
    from rag.utils import read_jsonl, update_status, write_jsonl

    site = [c for c in read_jsonl(settings.chunks_file, TextChunk) if not c.doc_id.startswith(DOC_PREFIX)] \
        if settings.chunks_file.exists() else []
    answers = answer_chunks(settings)
    write_jsonl(settings.chunks_file, site + answers)
    update_status(settings.status_file, "answers", answers=len(AnswerStore(settings.data_dir / "admin").all()),
                  chunks=len(answers))
    return len(answers)
