"""Hybrid retrieval: Qdrant semantic search + BM25, fused with RRF.

Text:   semantic top-N  +  BM25 top-N  ->  RRF  ->  de-duplicate  ->  (rerank)  ->  top-k
Images: semantic top-N over image chunks (caption/OCR/alt/description text)
        + BM25 top-N over the same text
        + "page-linked" ranking: images that live on the pages of the
          retrieved text chunks, ordered by that page's rank
        ->  RRF  ->  relevance gate  ->  top-k

The relevance gate keeps an image only if it matched the query lexically
(BM25) or semantically above ``image_min_semantic_score`` - being on a
relevant page alone is a fusion signal, never a reason to show an image.
Direct pixel-vector search is not used: the configured embedders are
text models, so images are retrieved through their textual evidence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rag.config import Settings
from rag.embeddings.base import Embedder
from rag.index.bm25 import BM25Index
from rag.index.qdrant_store import QdrantStore
from rag.models import RetrievedChunk, RetrievedImage
from rag.retrieval.corpus import Corpus
from rag.retrieval.rrf import reciprocal_rank_fusion

log = logging.getLogger(__name__)


@dataclass
class TextSearchResult:
    chunks: list[RetrievedChunk]
    best_semantic: float
    best_bm25: float

    @property
    def has_evidence(self) -> bool:
        return bool(self.chunks)


class Reranker:
    """Optional cross-encoder reranker (e.g. BAAI/bge-reranker-v2-m3)."""

    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder  # type: ignore

        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return chunks
        scores = self.model.predict([(query, c.text) for c in chunks])
        ranked = sorted(zip(chunks, scores), key=lambda pair: -float(pair[1]))
        return [c for c, _ in ranked]


class HybridRetriever:
    def __init__(self, settings: Settings, embedder: Embedder, store: QdrantStore, corpus: Corpus,
                 bm25_text: BM25Index, bm25_images: BM25Index, reranker: Reranker | None = None):
        self.settings = settings
        self.embedder = embedder
        self.store = store
        self.corpus = corpus
        self.bm25_text = bm25_text
        self.bm25_images = bm25_images
        self.reranker = reranker

    # ------------------------------------------------------------- text
    def search_text(self, query: str, top_k: int | None = None) -> TextSearchResult:
        s = self.settings
        top_k = top_k or s.retrieval_top_k
        vector = self.embedder.embed_query(query)
        semantic = self.store.search(s.qdrant_text_collection, vector, s.semantic_candidates)
        semantic = [(cid, score) for cid, score, _ in semantic if cid in self.corpus.chunks]
        keyword = [(cid, score) for cid, score in self.bm25_text.search(query, s.bm25_candidates) if cid in self.corpus.chunks]

        # Semantic hits below the floor are noise: they still help ordering
        # when BM25 agrees, but cannot introduce a chunk on their own.
        floor = s.text_min_semantic_score
        sem_rank = {cid: (i + 1, score) for i, (cid, score) in enumerate(semantic)}
        bm_rank = {cid: (i + 1, score) for i, (cid, score) in enumerate(keyword)}
        # Third ranking: how much of the question's (IDF-weighted) vocabulary each candidate contains.
        candidates = list(dict.fromkeys([c for c, _ in semantic] + [c for c, _ in keyword]))
        coverage = {cid: self.bm25_text.coverage(query, cid) for cid in candidates}
        by_coverage = sorted(candidates, key=lambda c: -coverage[c])
        # Field boost: the question's terms in the page title / section headings ("Contact Us").
        def title_text(cid: str) -> str:
            chunk = self.corpus.chunks[cid]
            return " ".join([chunk.page_title.split(" – ")[0].split(" | ")[0], *chunk.heading_path])
        title_match = {cid: self.bm25_text.weighted_overlap(query, title_text(cid)) for cid in candidates}
        fused = reciprocal_rank_fusion([[c for c, _ in semantic], [c for c, _ in keyword], by_coverage], k=s.rrf_k)
        # Tie-breakers, not ranking lists: a mild prior by page type (official pages over news
        # posts) and a small boost when the question's terms appear in the page title/headings.
        weights = s.kind_weights
        fused = sorted(((cid, score * weights.get(self.corpus.chunks[cid].metadata.get("kind", "page"), 1.0)
                         * (1.0 + s.title_boost * title_match[cid])) for cid, score in fused), key=lambda x: -x[1])

        results: list[RetrievedChunk] = []
        seen_hashes: set[str] = set()
        for cid, score in fused:
            sem = sem_rank.get(cid)
            bm = bm_rank.get(cid)
            semantic_ok = sem is not None and sem[1] >= floor
            if not semantic_ok and (bm is None or coverage[cid] < s.min_query_coverage):
                continue  # weak lexical overlap and no semantic support
            chunk = self.corpus.chunks[cid]
            if chunk.content_hash in seen_hashes:
                continue
            seen_hashes.add(chunk.content_hash)
            results.append(RetrievedChunk(
                chunk_id=cid, doc_id=chunk.doc_id, url=chunk.url, page_title=chunk.page_title,
                heading_path=chunk.heading_path, text=chunk.text, score=round(score, 6),
                semantic_rank=sem[0] if sem else None, semantic_score=round(sem[1], 4) if sem else None,
                bm25_rank=bm[0] if bm else None, bm25_score=round(bm[1], 4) if bm else None,
            ))
            if len(results) >= top_k * (3 if self.reranker else 1):
                break
        if self.reranker:
            results = self.reranker.rerank(query, results)[:top_k]
        return TextSearchResult(
            chunks=results[:top_k],
            best_semantic=max((s_ for _, s_ in semantic), default=0.0),
            best_bm25=max((s_ for _, s_ in keyword), default=0.0),
        )

    # ------------------------------------------------------------- images
    def search_images(self, query: str, top_k: int | None = None,
                      text_results: list[RetrievedChunk] | None = None) -> list[RetrievedImage]:
        s = self.settings
        top_k = top_k or s.image_top_k
        if not self.corpus.image_chunks:
            return []
        vector = self.embedder.embed_query(query)
        semantic = [(cid, score) for cid, score, _ in self.store.search(s.qdrant_image_collection, vector, s.semantic_candidates)
                    if cid in self.corpus.image_chunks]
        keyword = [(cid, score) for cid, score in self.bm25_images.search(query, s.bm25_candidates) if cid in self.corpus.image_chunks]

        page_linked: list[str] = []
        for chunk in text_results or []:
            for image_id in self.corpus.images_by_page.get(chunk.url, []):
                if image_id not in page_linked:
                    page_linked.append(image_id)

        sem_score = dict(semantic)
        bm_score = dict(keyword)
        fused = reciprocal_rank_fusion([[c for c, _ in semantic], [c for c, _ in keyword], page_linked], k=s.rrf_k,
                                       weights=[1.0, 1.0, 0.5])
        images: list[RetrievedImage] = []
        for image_id, score in fused:
            lexical = image_id in bm_score
            semantic_ok = sem_score.get(image_id, 0.0) >= s.image_min_semantic_score
            if not (lexical or semantic_ok):
                continue
            chunk = self.corpus.image_chunks[image_id]
            meta = chunk.metadata
            images.append(RetrievedImage(
                image_id=image_id, url=chunk.url, source_page=chunk.source_page, page_title=chunk.page_title,
                heading=chunk.heading, alt=meta.get("alt", ""), caption=meta.get("caption", ""),
                ocr_text=meta.get("ocr_text", ""), description=meta.get("description", ""),
                description_model=meta.get("description_model", ""), width=meta.get("width", 0),
                height=meta.get("height", 0), score=round(score, 6),
                semantic_score=round(sem_score[image_id], 4) if image_id in sem_score else None,
                bm25_score=round(bm_score[image_id], 4) if image_id in bm_score else None,
            ))
            if len(images) >= top_k:
                break
        return images
