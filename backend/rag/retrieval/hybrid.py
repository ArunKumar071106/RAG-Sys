"""Hybrid retrieval: Qdrant semantic search + BM25, fused with RRF.

Text:   semantic top-N  +  BM25 top-N  +  title/headings BM25 top-N  +  coverage  ->  RRF  ->  de-duplicate  ->  (rerank)  ->  top-k
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
import re
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlsplit

import numpy as np

from rag.config import Settings
from rag.embeddings.base import Embedder
from rag.index.bm25 import BM25Index, tokenize
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


# Words that ask for a kind of answer ("show me photos of ...") rather than describing the topic.
_REQUEST_WORDS_RE = re.compile(
    r"\b(show( me)?|display|photos?|pictures?|pics?|images?|gallery|look(s)? like|view of|available|availability)\b", re.I
)
# Words too common to make a phrase: "counselling code" and "required documents" are phrases,
# "is the" is not.
_PHRASE_STOP = {"a", "an", "the", "of", "and", "or", "is", "are", "was", "were", "for", "to", "in", "on", "at", "by",
                "with", "what", "which", "who", "whom", "how", "when", "where", "why", "do", "does", "did", "can",
                "i", "me", "my", "you", "your", "there", "any", "it", "its", "this", "that", "be", "should", "will",
                "about", "tell", "give", "list", "please", "college", "aaacet", "aaa"}


_LABEL_RE = re.compile(r"^\s*[-*•]?\s*([A-Za-z][A-Za-z .&/()'-]{1,40}?)\s*:\s*\S")


def labelled_fact_hits(text: str, q_tokens: set[str]) -> int:
    """How many different "Label: value" labels - on their own line, or as a table cell
    ("INTAKE: 120") - are made only of question words."""
    found: set[frozenset[str]] = set()
    for line in text.splitlines():
        for cell in line.split(" | "):
            match = _LABEL_RE.match(cell)
            if match:
                label = frozenset(tokenize(match.group(1))) - {"the", "of", "and"}
                if label and label <= q_tokens:
                    found.add(label)
    return len(found)


def query_phrases(query: str) -> list[str]:
    """Adjacent topical word pairs of a question: "What is the TNEA counselling code?" ->
    ["tnea counselling", "counselling code"]. A chunk containing the exact phrase is about it."""
    words = re.findall(r"[a-z0-9][a-z0-9.&'-]*", query.lower())
    pairs = []
    for a, b in zip(words, words[1:]):
        if a not in _PHRASE_STOP and b not in _PHRASE_STOP and len(a) > 1 and len(b) > 1:
            pairs.append(f"{a} {b}")
    return list(dict.fromkeys(pairs))


def content_query(query: str) -> str:
    """The topical part of a question: "Show photos of the hostel" -> "of the hostel"."""
    stripped = re.sub(r"\s+", " ", _REQUEST_WORDS_RE.sub(" ", query)).strip()
    return stripped if re.search(r"\w{3,}", stripped) else query


_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.M)


def chunk_title_text(chunk) -> str:
    """The page title (without the site-name suffix), the URL path words, the chunk's section path and
    the headings inside it: "/civil/faculty-list/" says which department a "Faculty List" page belongs
    to, and a chunk holding several short sections ("Required Documents", "Reservation Policy") is
    found by each of their names."""
    path_words = re.sub(r"[-_/]+", " ", urlsplit(chunk.url).path).strip()
    inner = [h for h in _MD_HEADING_RE.findall(chunk.text) if h not in chunk.heading_path]
    return " ".join([chunk.page_title.split(" – ")[0].split(" | ")[0], path_words, *chunk.heading_path, *inner])


def expand_query(query: str, expansions: dict[str, str]) -> str:
    """Replace short forms in the question with the names the website uses: "AI&DS faculty"
    searches "Artificial Intelligence and Data Science faculty". Replacing (not appending)
    matters: event posts repeat "AI&DS" in student class names ("III AI&DS"), while the
    department's own pages use the full name."""
    for pattern, expansion in expansions.items():
        query = re.sub(rf"(?<![\w&])(?:{pattern})(?![\w&])", expansion, query, flags=re.I)
    return query


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
        # False while the vector index is still being built: rank with the keyword lists only.
        self.semantic_enabled = True
        # Field index over page titles and section headings: "Who is the principal?" should
        # find the "Principal Message" page even when news posts mention the principal more.
        self.bm25_titles = BM25Index.build([(cid, chunk_title_text(chunk)) for cid, chunk in corpus.chunks.items()])
        # Over the network (Qdrant Cloud) the image search for a question starts with its text search,
        # so a question waits for one round trip instead of two; search_images picks the result up.
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qdrant") if getattr(store, "remote", False) else None
        self._image_hits: OrderedDict[str, Future] = OrderedDict()
        self._vectors: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    def _query_vector(self, query: str) -> np.ndarray:
        """The query's embedding, computed once for its text and image searches."""
        with self._lock:
            if query in self._vectors:
                return self._vectors[query]
        vector = self.embedder.embed_query(query)
        with self._lock:
            self._vectors[query] = vector
            while len(self._vectors) > 64:
                self._vectors.popitem(last=False)
        return vector

    def _image_semantic(self, query: str, vector: np.ndarray) -> list[tuple[str, float]]:
        s = self.settings
        return [(cid, score) for cid, score, _ in self.store.search(s.qdrant_image_collection, vector, s.semantic_candidates)
                if cid in self.corpus.image_chunks]

    def normalize_query(self, query: str) -> str:
        """What is searched for: request words dropped, short forms spelled out the website's way,
        "department" dropped when a department is named (it is implied, and "About Department"
        pages would otherwise outrank the department's "Faculty List"), and words the website uses
        for the question's intent added ("where is the college" -> "address")."""
        text = expand_query(content_query(query), self.settings.query_expansions)
        lowered = text.lower()
        named = [d for d in self.settings.departments if d.lower() in lowered]
        if named:
            # "faculty of the Civil Engineering department": the department is implied, and "About
            # Department" pages would outrank its "Faculty List"; but in "Tell me about the CSE
            # department" the department itself is the topic, so the word stays
            rest = re.sub(r"\bdepartments?\b", " ", lowered.replace(max(named, key=len).lower(), " "))
            if any(w not in _PHRASE_STOP for w in re.findall(r"[a-z]{3,}", rest)):
                text = re.sub(r"\bdepartments?\b", " ", text, flags=re.I)
        extra = [words for pattern, words in self.settings.query_synonyms.items() if re.search(pattern, text, re.I)
                 and words.lower() not in lowered]
        return re.sub(r"\s+", " ", " ".join([text, *extra])).strip()

    # ------------------------------------------------------------- text
    def search_text(self, query: str, top_k: int | None = None) -> TextSearchResult:
        s = self.settings
        top_k = top_k or s.retrieval_top_k
        query = self.normalize_query(query)
        semantic: list[tuple[str, float]] = []
        if self.semantic_enabled:
            vector = self._query_vector(query)
            if self._pool is not None and self.corpus.image_chunks:
                future = self._pool.submit(self._image_semantic, query, vector)
                with self._lock:
                    self._image_hits[query] = future
                    while len(self._image_hits) > 64:
                        self._image_hits.popitem(last=False)
            semantic = [(cid, score) for cid, score, _ in self.store.search(s.qdrant_text_collection, vector, s.semantic_candidates)
                        if cid in self.corpus.chunks]
        keyword = [(cid, score) for cid, score in self.bm25_text.search(query, s.bm25_candidates) if cid in self.corpus.chunks]

        # Semantic hits below the floor are noise: they still help ordering
        # when BM25 agrees, but cannot introduce a chunk on their own.
        floor = s.text_min_semantic_score
        sem_rank = {cid: (i + 1, score) for i, (cid, score) in enumerate(semantic)}
        bm_rank = {cid: (i + 1, score) for i, (cid, score) in enumerate(keyword)}
        # Title/headings ranking, kept only where the title itself covers enough of the question
        # (the same bar as a lexical-only hit), so "Computer Science" in a title does not pull
        # that page into a question about the Data Science fee.
        title_match: dict[str, float] = {}
        titled: list[str] = []
        if s.title_rank_weight > 0:
            for cid, _ in self.bm25_titles.search(query, s.bm25_candidates):
                chunk = self.corpus.chunks.get(cid)
                if chunk is None:
                    continue
                title_match[cid] = self.bm25_text.weighted_overlap(query, chunk_title_text(chunk))
                if title_match[cid] >= s.min_query_coverage:
                    titled.append(cid)
        title_ranked = set(titled)
        # Third ranking: how much of the question's (IDF-weighted) vocabulary each candidate contains.
        # Chunks with the question's rarest words: "intake" in "intake for AI&DS" is what the answer
        # has, while the department name is on a hundred pages.
        rare = self.bm25_text.rare_terms(query, 2)
        rare_hits = [cid for cid, _ in self.bm25_text.search(" ".join(rare), s.bm25_candidates)
                     if cid in self.corpus.chunks] if rare else []
        rare_set = set(rare_hits)
        candidates = list(dict.fromkeys([c for c, _ in semantic] + [c for c, _ in keyword] + titled + rare_hits))
        coverage = {cid: self.bm25_text.coverage(query, cid) for cid in candidates}
        by_coverage = sorted(candidates, key=lambda c: -coverage[c])
        # Field boost: the question's terms in the page title / section headings ("Contact Us").
        for cid in candidates:
            if cid not in title_match:
                title_match[cid] = self.bm25_text.weighted_overlap(query, chunk_title_text(self.corpus.chunks[cid]))
        # Fourth ranking: chunks containing the question's exact word pairs ("counselling code",
        # "required documents", "academic performance").
        phrases = query_phrases(query)
        texts = {cid: re.sub(r"\s+", " ", self.corpus.chunks[cid].text.lower()) for cid in candidates} if phrases else {}
        # only distinctive phrases count: "faculty members" is in every news post
        phrases = [p for p in phrases if sum(p in t for t in texts.values()) <= max(3, len(candidates) // 5)]
        phrase_hits = {cid: sum(p in texts[cid] for p in phrases) for cid in candidates} if phrases else {}
        by_phrase = sorted((c for c in candidates if phrase_hits.get(c)), key=lambda c: -phrase_hits[c])
        # Fifth: "Label: value" facts whose label the question names ("COUNSELLING CODE : 4680",
        # "Address: ...", "Phone: ...") - the website's headers, footers and labelled table rows.
        q_tokens = set(tokenize(query))
        label_hits = {cid: labelled_fact_hits(self.corpus.chunks[cid].text, q_tokens) for cid in candidates}
        by_label = sorted((c for c in candidates if label_hits[c]), key=lambda c: -label_hits[c])
        fused = reciprocal_rank_fusion([[c for c, _ in semantic], [c for c, _ in keyword], by_coverage, by_phrase], k=s.rrf_k)
        # A label the question names is a precise match: it counts like the title ranking does.
        label_rrf = {cid: s.label_rank_weight / (s.rrf_k + rank) for rank, cid in enumerate(by_label, start=1)}
        fused = [(cid, score + label_rrf.pop(cid, 0.0)) for cid, score in fused] + list(label_rrf.items())
        # The title ranking counts in proportion to how much of the question the title covers.
        title_rrf = {cid: s.title_rank_weight * title_match[cid] ** 2 / (s.rrf_k + rank) for rank, cid in enumerate(titled, start=1)}
        fused = [(cid, score + title_rrf.pop(cid, 0.0)) for cid, score in fused] + list(title_rrf.items())
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
            lexical = bm is not None or cid in title_ranked or cid in rare_set
            if not semantic_ok and (not lexical or coverage[cid] < s.min_query_coverage):
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

    def expand_section(self, chunks: list[RetrievedChunk], max_chunks: int | None = None,
                       max_sections: int = 2) -> list[RetrievedChunk]:
        """Complete the sections the results point at, in page order.

        A long table is split over several chunks; a question like "AI&DS faculty names"
        matches some of them, but the answer needs every row. A section is completed when it
        holds the best match or at least two of the matches (at most ``max_sections`` sections,
        ``max_chunks`` chunks each); every other result keeps its place.
        """
        max_chunks = self.settings.section_expand_max if max_chunks is None else max_chunks
        if not chunks or max_chunks <= 1:
            return chunks
        key = lambda c: (c.doc_id, tuple(c.heading_path))  # noqa: E731
        hits: dict[tuple, list[str]] = {}
        for c in chunks:
            hits.setdefault(key(c), []).append(c.chunk_id)
        by_id = {c.chunk_id: c for c in chunks}
        expanded: list[RetrievedChunk] = []
        placed: set[str] = set()
        done: set[tuple] = set()
        for position, c in enumerate(chunks):
            if c.chunk_id in placed:
                continue
            k = key(c)
            section = self.corpus.sections.get(k, [])
            # only tables are completed: a long prose section (a page of NAAC criteria) would push
            # the result that answers the question out of the top sources
            if k not in done and len(done) < max_sections and len(section) > 1 and c.chunk_id in section \
                    and " | " in c.text and (position == 0 or len(hits[k]) >= 2):
                done.add(k)
                anchor = min(section.index(cid) for cid in hits[k] if cid in section)
                start = max(0, min(anchor, len(section) - max_chunks))
                for cid in section[start:start + max_chunks]:
                    if cid in placed:
                        continue
                    if cid in by_id:
                        expanded.append(by_id[cid])
                    else:
                        part = self.corpus.chunks[cid]
                        expanded.append(RetrievedChunk(chunk_id=cid, doc_id=part.doc_id, url=part.url, page_title=part.page_title,
                                                       heading_path=part.heading_path, text=part.text, score=c.score))
                    placed.add(cid)
                if c.chunk_id in placed:
                    continue
            expanded.append(c)
            placed.add(c.chunk_id)
        return expanded

    # ------------------------------------------------------------- images
    def search_images(self, query: str, top_k: int | None = None,
                      text_results: list[RetrievedChunk] | None = None) -> list[RetrievedImage]:
        s = self.settings
        top_k = top_k or s.image_top_k
        if not self.corpus.image_chunks:
            return []
        query = self.normalize_query(query)
        semantic: list[tuple[str, float]] = []
        if self.semantic_enabled:
            with self._lock:
                future = self._image_hits.pop(query, None)
            semantic = future.result() if future is not None else self._image_semantic(query, self._query_vector(query))
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
        # same page-type prior as text: photos on official pages before news-post photos
        fused = sorted(((iid, score * s.kind_weights.get(self.corpus.page_kinds.get(
            self.corpus.image_chunks[iid].source_page, "page"), 1.0)) for iid, score in fused), key=lambda x: -x[1])
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
