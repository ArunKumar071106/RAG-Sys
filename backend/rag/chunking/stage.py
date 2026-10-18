"""Chunking stage: documents -> text chunks (JSONL) with cross-page duplicate detection."""

from __future__ import annotations

import logging

from rag.chunking.text_chunker import StructureAwareChunker
from rag.config import Settings
from rag.extraction.stage import load_duplicates
from rag.models import PageDocument, TextChunk
from rag.utils import read_jsonl, update_status, write_jsonl

log = logging.getLogger(__name__)


def dedupe_chunks(chunks: list[TextChunk]) -> tuple[list[TextChunk], int]:
    """Drop chunks whose exact text already exists on another page.

    The surviving chunk remembers the other URLs in ``duplicate_urls``.
    """
    kept: dict[str, TextChunk] = {}
    removed = 0
    for chunk in chunks:
        existing = kept.get(chunk.content_hash)
        if existing is None:
            kept[chunk.content_hash] = chunk
        else:
            removed += 1
            if chunk.url != existing.url and chunk.url not in existing.duplicate_urls:
                existing.duplicate_urls.append(chunk.url)
    return list(kept.values()), removed


def run_chunking(settings: Settings) -> list[TextChunk]:
    chunker = StructureAwareChunker(
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
        min_tokens=settings.chunk_min_tokens,
    )
    duplicates = load_duplicates(settings)
    chunks: list[TextChunk] = []
    docs = 0
    for doc in read_jsonl(settings.documents_file, PageDocument):
        docs += 1
        chunks.extend(chunker.chunk_document(doc, duplicates.get(doc.url)))
    chunks, removed = dedupe_chunks(chunks)
    write_jsonl(settings.chunks_file, chunks)
    avg = round(sum(c.token_count for c in chunks) / len(chunks), 1) if chunks else 0
    update_status(settings.status_file, "chunk", documents=docs, chunks=len(chunks), duplicate_chunks=removed, avg_tokens=avg)
    log.info("Chunked %d documents into %d chunks (%d duplicates removed)", docs, len(chunks), removed)
    return chunks
