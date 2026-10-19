"""In-memory lookup of chunks and image records loaded from the processed JSONL files."""

from __future__ import annotations

from dataclasses import dataclass, field

from rag.config import Settings
from rag.models import ImageChunk, ImageRecord, TextChunk
from rag.utils import read_jsonl


@dataclass
class Corpus:
    chunks: dict[str, TextChunk] = field(default_factory=dict)
    image_chunks: dict[str, ImageChunk] = field(default_factory=dict)
    images: dict[str, ImageRecord] = field(default_factory=dict)
    images_by_page: dict[str, list[str]] = field(default_factory=dict)
    page_kinds: dict[str, str] = field(default_factory=dict)  # url -> page | section | news | document
    # (doc_id, heading_path) -> chunk ids in page order: one section split over several chunks (e.g. a long table)
    sections: dict[tuple[str, tuple[str, ...]], list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, settings: Settings) -> Corpus:
        corpus = cls()
        corpus.chunks = {c.chunk_id: c for c in read_jsonl(settings.chunks_file, TextChunk)}
        corpus.image_chunks = {c.chunk_id: c for c in read_jsonl(settings.image_chunks_file, ImageChunk)}
        corpus.images = {r.image_id: r for r in read_jsonl(settings.images_file, ImageRecord)}
        corpus.page_kinds = {c.url: c.metadata.get("kind", "page") for c in corpus.chunks.values()}
        for chunk in corpus.image_chunks.values():
            record = corpus.images.get(chunk.image_id)
            pages = [chunk.source_page, *(record.also_on_pages if record else [])]
            for page in pages:
                corpus.images_by_page.setdefault(page, []).append(chunk.image_id)
        for chunk in sorted(corpus.chunks.values(), key=lambda c: c.chunk_index):
            corpus.sections.setdefault((chunk.doc_id, tuple(chunk.heading_path)), []).append(chunk.chunk_id)
        return corpus
