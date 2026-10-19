"""Initial and incremental indexing into Qdrant + BM25, with validation.

Incremental mode compares a fingerprint per document (and per image) with
the previous manifest and only re-embeds what changed; removed documents
are deleted. Switching embedding model or dimension forces a full rebuild
so vectors from different models are never mixed.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable

from rag.config import Settings
from rag.embeddings.base import Embedder
from rag.index.bm25 import BM25Index
from rag.index.qdrant_store import QdrantStore
from rag.models import ImageChunk, TextChunk
from rag.utils import read_json, read_jsonl, sha256_text, update_status, utc_now, write_json

log = logging.getLogger(__name__)


def manifest_path(settings: Settings):
    return settings.index_dir / "manifest.json"


def bm25_text_path(settings: Settings):
    return settings.index_dir / "bm25_text.json"


def bm25_image_path(settings: Settings):
    return settings.index_dir / "bm25_images.json"


def _text_payload(chunk: TextChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "url": chunk.url,
        "page_title": chunk.page_title,
        "heading_path": chunk.heading_path,
        "text": chunk.text,
        "content_hash": chunk.content_hash,
        "duplicate_urls": chunk.duplicate_urls,
    }


def _image_payload(chunk: ImageChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "image_id": chunk.image_id,
        "url": chunk.url,
        "source_page": chunk.source_page,
        "page_title": chunk.page_title,
        "heading": chunk.heading,
        "text": chunk.text,
        "content_hash": chunk.content_hash,
        **{k: v for k, v in chunk.metadata.items() if k != "local_path"},
    }


def build_bm25_indexes(settings: Settings, text_chunks: list[TextChunk] | None = None,
                       image_chunks: list[ImageChunk] | None = None) -> None:
    """(Re)build both keyword indexes from the processed chunks; takes seconds, no embedding."""
    if text_chunks is None:
        text_chunks = list(read_jsonl(settings.chunks_file, TextChunk))
    if image_chunks is None:
        image_chunks = list(read_jsonl(settings.image_chunks_file, ImageChunk))
    BM25Index.build([(c.chunk_id, c.embedding_text()) for c in text_chunks]).save(bm25_text_path(settings))
    BM25Index.build([(c.chunk_id, c.text) for c in image_chunks]).save(bm25_image_path(settings))


def data_fingerprint(settings: Settings) -> str:
    """Hash of the processed chunk files, to notice an updated knowledge base (e.g. after a git pull)."""
    digest = hashlib.sha256()
    for path in (settings.chunks_file, settings.image_chunks_file):
        if path.exists():
            with path.open("rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


class Indexer:
    def __init__(self, settings: Settings, embedder: Embedder, store: QdrantStore,
                 progress: Callable[[str, int, int], None] | None = None):
        self.settings = settings
        self.embedder = embedder
        self.store = store
        self.progress = progress
        self._skip_existing = False

    FULL_REBUILD = ("first start or embedder change", "empty index")

    @staticmethod
    def build_needed(settings: Settings, embedder: Embedder, store: QdrantStore) -> str:
        """Why the vector index must be (re)built before semantic search can be used, or "" if it is current.

        Reasons in ``FULL_REBUILD`` need every chunk embedded; the others (an interrupted build, an
        updated data/processed after a pull) only re-embed what is missing or changed.
        """
        if not settings.chunks_file.exists():
            return ""
        manifest = read_json(manifest_path(settings))
        if manifest.get("embedder") != embedder.name or manifest.get("dim") != embedder.dim:
            return "first start or embedder change"
        if manifest.get("complete", True) is False:
            return "an interrupted build"
        if store.count(settings.qdrant_text_collection) == 0:
            return "empty index"
        if manifest.get("data") != data_fingerprint(settings):
            return "the knowledge base changed"
        return ""

    def run(self, full: bool = False) -> dict:
        s = self.settings
        s.ensure_dirs()
        manifest = read_json(manifest_path(s))
        if manifest and (manifest.get("embedder") != self.embedder.name or manifest.get("dim") != self.embedder.dim):
            log.warning("Embedder changed (%s -> %s); performing a full reindex", manifest.get("embedder"), self.embedder.name)
            full = True
        if full:
            manifest = {}
        # A build that stopped part-way (same embedder) resumes: vectors already stored are kept.
        self._skip_existing = manifest.get("complete", True) is False
        if self._skip_existing:
            log.info("Resuming an interrupted index build")
        update_status(s.status_file, "index", state="running", mode="full" if full else "incremental", started_at=utc_now())

        text_chunks = list(read_jsonl(s.chunks_file, TextChunk))
        image_chunks = list(read_jsonl(s.image_chunks_file, ImageChunk))

        self.store.ensure_collection(s.qdrant_text_collection, self.embedder.dim, recreate=full)
        self.store.ensure_collection(s.qdrant_image_collection, self.embedder.dim, recreate=full)
        write_json(manifest_path(s), {**manifest, "embedder": self.embedder.name, "dim": self.embedder.dim, "complete": False})

        text_report, text_docs = self._index_text(text_chunks, manifest.get("text_docs", {}))
        image_report, image_items = self._index_images(image_chunks, manifest.get("image_items", {}))

        build_bm25_indexes(s, text_chunks, image_chunks)

        validation = self.validate(text_chunks, image_chunks)
        new_manifest = {
            "embedder": self.embedder.name,
            "dim": self.embedder.dim,
            "text_collection": s.qdrant_text_collection,
            "image_collection": s.qdrant_image_collection,
            "indexed_at": utc_now(),
            "text_docs": text_docs,
            "image_items": image_items,
            "counts": {"text_chunks": len(text_chunks), "image_chunks": len(image_chunks)},
            "data": data_fingerprint(s),
            "complete": True,
        }
        write_json(manifest_path(s), new_manifest)
        report = {"mode": "full" if full else "incremental", "text": text_report, "images": image_report, "validation": validation}
        update_status(s.status_file, "index", state="finished" if validation["ok"] else "invalid", finished_at=utc_now(),
                      **{f"text_{k}": v for k, v in text_report.items()}, **{f"images_{k}": v for k, v in image_report.items()},
                      validation_ok=validation["ok"], embedder=self.embedder.name)
        log.info("Index report: %s", report)
        return report

    # ------------------------------------------------------------- text
    def _index_text(self, chunks: list[TextChunk], previous: dict) -> tuple[dict, dict]:
        name = self.settings.qdrant_text_collection
        by_doc: dict[str, list[TextChunk]] = defaultdict(list)
        for chunk in chunks:
            by_doc[chunk.doc_id].append(chunk)

        current: dict[str, dict] = {}
        changed: list[TextChunk] = []
        unchanged = 0
        stale_ids: list[str] = []
        for doc_id, doc_chunks in by_doc.items():
            # the embedded text includes the page title and headings, so a retitled page is re-embedded
            fingerprint = sha256_text("|".join(f"{c.chunk_id}:{sha256_text(c.embedding_text())}:{','.join(c.duplicate_urls)}"
                                               for c in doc_chunks))
            current[doc_id] = {"fingerprint": fingerprint, "chunk_ids": [c.chunk_id for c in doc_chunks]}
            old = previous.get(doc_id)
            if old and old.get("fingerprint") == fingerprint:
                unchanged += 1
                continue
            if old:
                stale_ids.extend(set(old.get("chunk_ids", [])) - set(current[doc_id]["chunk_ids"]))
            changed.extend(doc_chunks)
        removed_docs = [d for d in previous if d not in current]
        for doc_id in removed_docs:
            stale_ids.extend(previous[doc_id].get("chunk_ids", []))

        self.store.delete_ids(name, stale_ids)
        self._embed_and_upsert(name, [c.chunk_id for c in changed], [c.embedding_text() for c in changed],
                               [_text_payload(c) for c in changed])
        return {"documents": len(by_doc), "changed_documents": len({c.doc_id for c in changed}),
                "unchanged_documents": unchanged, "removed_documents": len(removed_docs),
                "upserted": len(changed), "deleted": len(stale_ids)}, current

    # ------------------------------------------------------------- images
    def _index_images(self, chunks: list[ImageChunk], previous: dict) -> tuple[dict, dict]:
        name = self.settings.qdrant_image_collection
        current = {c.chunk_id: c.content_hash for c in chunks}
        changed = [c for c in chunks if previous.get(c.chunk_id) != c.content_hash]
        removed = [cid for cid in previous if cid not in current]
        self.store.delete_ids(name, removed)
        self._embed_and_upsert(name, [c.chunk_id for c in changed], [c.text for c in changed], [_image_payload(c) for c in changed])
        return {"images": len(chunks), "upserted": len(changed), "deleted": len(removed)}, current

    def _embed_and_upsert(self, name: str, ids: list[str], texts: list[str], payloads: list[dict]) -> None:
        total = len(ids)
        skipped = 0
        if self._skip_existing:
            existing = self.store.existing_ids(name, ids)
            keep = [i for i, cid in enumerate(ids) if cid not in existing]
            skipped = total - len(keep)
            ids, texts, payloads = [ids[i] for i in keep], [texts[i] for i in keep], [payloads[i] for i in keep]
            if skipped:
                log.info("Indexing %s: %d/%d already done", name, skipped, total)
        batch = max(1, self.settings.embedding_batch_size * 4)
        next_report = 0.1
        for start in range(0, len(ids), batch):
            vectors = self.embedder.embed_documents(texts[start:start + batch])
            if vectors.shape[1] != self.embedder.dim:
                raise RuntimeError(f"Embedder returned {vectors.shape[1]}-d vectors, expected {self.embedder.dim}")
            self.store.upsert(name, ids[start:start + batch], vectors, payloads[start:start + batch])
            done = skipped + min(start + batch, len(ids))
            if self.progress:
                self.progress(name, done, total)
            if done == total or done / total >= next_report:
                log.info("Indexing %s: %d/%d (%d%%)", name, done, total, 100 * done // total)
                next_report = done / total + 0.1

    # ------------------------------------------------------------- validation
    def validate(self, text_chunks: list[TextChunk], image_chunks: list[ImageChunk], samples: int = 5) -> dict:
        s = self.settings
        text_count = self.store.count(s.qdrant_text_collection)
        image_count = self.store.count(s.qdrant_image_collection)
        problems: list[str] = []
        if text_count != len(text_chunks):
            problems.append(f"text collection has {text_count} points, expected {len(text_chunks)}")
        if image_count != len(image_chunks):
            problems.append(f"image collection has {image_count} points, expected {len(image_chunks)}")
        dim = self.store.collection_dim(s.qdrant_text_collection)
        if dim is not None and dim != self.embedder.dim:
            problems.append(f"text collection dimension {dim} != embedder dimension {self.embedder.dim}")
        step = max(1, len(text_chunks) // samples) if text_chunks else 1
        self_hits = 0
        probes = text_chunks[::step][:samples]
        for chunk in probes:
            vector = self.embedder.embed_query(chunk.embedding_text())
            hits = self.store.search(s.qdrant_text_collection, vector, 3)
            if any(h[0] == chunk.chunk_id for h in hits):
                self_hits += 1
        if probes and self_hits < len(probes):
            problems.append(f"only {self_hits}/{len(probes)} probe chunks retrieved themselves")
        return {"ok": not problems, "text_points": text_count, "image_points": image_count, "problems": problems}
