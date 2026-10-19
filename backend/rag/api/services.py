"""Long-lived service objects shared by API requests, with hot reload after reindexing."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field

from rag.config import Settings
from rag.utils import utc_now

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    mode: str
    stages: list[str]
    state: str = "queued"  # queued | running | finished | failed
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    report: dict = field(default_factory=dict)


class Services:
    """Owns the embedder, Qdrant connection, corpus and retriever.

    Construction never raises: if a component cannot be loaded (e.g. the
    embedding model is unavailable) the error is kept in ``self.error`` and
    surfaced by /api/health, while chat endpoints answer 503.
    """

    def __init__(self, settings: Settings, embedder=None, store=None, llm=None, load_llm: bool = True,
                 background: bool = False):
        self.settings = settings
        self.embedder = embedder
        self.store = store
        self.llm = llm
        self._load_llm = load_llm and llm is None
        self.corpus = None
        self.retriever = None
        self.answers = None
        self.error = ""
        self.index_error = ""
        self.indexing = False
        self.index_progress: dict = {}
        self.jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._job_lock = threading.Lock()
        # In the API the first load (which may build the whole index) runs in the background,
        # so the server starts at once and answers "starting up" instead of refusing connections.
        self.starting = background
        if background:
            threading.Thread(target=self._initial_load, daemon=True, name="rag-startup").start()
        else:
            self.load()

    def _initial_load(self) -> None:
        try:
            self.load(defer_vectors=True)
        finally:
            self.starting = False
            self.indexing = False

    # ------------------------------------------------------------ lifecycle
    def load(self, defer_vectors: bool = False) -> None:
        """(Re)load everything. When the vector index must be built first and ``defer_vectors``
        is set (API startup), answer with keyword search right away and switch to hybrid
        search once the build finishes - on a laptop CPU it can take a long time."""
        from rag.embeddings import get_embedder
        from rag.index.indexer import Indexer
        from rag.index.qdrant_store import QdrantStore
        from rag.llm.client import get_llm

        with self._lock:
            try:
                if self.embedder is None:
                    self.embedder = get_embedder(self.settings)
                if self.store is None:
                    self.store = QdrantStore.from_settings(self.settings)
                if self._load_llm:
                    self.llm = get_llm(self.settings)
                    self._load_llm = False
                reason = Indexer.build_needed(self.settings, self.embedder, self.store) if self.settings.auto_index_on_startup else ""
                if reason and defer_vectors:
                    self._ensure_keyword_index(force=True)  # seconds; matches the current data/processed
                    self._build_answers(semantic=False)
                    self.error = ""
                    self.indexing, self.starting = True, False
                    log.info("Answering with keyword search while the semantic index is built (%s)", reason)
                    try:
                        self._build_vector_index(reason)
                        self._build_answers(semantic=True)
                        self.index_error = ""
                        log.info("Semantic index ready; answering with hybrid search")
                    except Exception as exc:
                        log.exception("Building the semantic index failed; keeping keyword search")
                        self.index_error = f"{type(exc).__name__}: {exc}"
                    finally:
                        self.indexing = False
                    return
                if reason:
                    self._build_vector_index(reason)
                else:
                    self._ensure_keyword_index()
                self._build_answers(semantic=True)
                self.error = self.index_error = ""
            except Exception as exc:
                log.exception("Failed to load RAG services")
                self.error = f"{type(exc).__name__}: {exc}"

    def _build_answers(self, semantic: bool) -> None:
        from rag.index.bm25 import BM25Index
        from rag.index.indexer import bm25_image_path, bm25_text_path
        from rag.llm.answer import AnswerService
        from rag.retrieval.corpus import Corpus
        from rag.retrieval.hybrid import HybridRetriever, Reranker

        corpus = Corpus.load(self.settings)
        reranker = None
        if self.settings.rerank_enabled:
            try:
                reranker = Reranker(self.settings.rerank_model)
            except Exception as exc:
                log.warning("Reranker unavailable: %s", exc)
        retriever = HybridRetriever(
            self.settings, self.embedder, self.store, corpus,
            BM25Index.load(bm25_text_path(self.settings)), BM25Index.load(bm25_image_path(self.settings)), reranker,
        )
        retriever.semantic_enabled = semantic
        answers = AnswerService(retriever, self.llm, self.settings.llm_history_turns,
                                self.settings.retrieval_top_k, self.settings.image_top_k)
        self.corpus, self.retriever, self.answers = corpus, retriever, answers

    def _ensure_keyword_index(self, force: bool = False) -> None:
        """BM25 indexes take seconds to build from data/processed; rebuild if missing or from an older tokenizer."""
        from rag.index.bm25 import BM25Index
        from rag.index.indexer import bm25_image_path, bm25_text_path, build_bm25_indexes

        s = self.settings
        if s.chunks_file.exists() and (force or not (BM25Index.is_current(bm25_text_path(s)) and BM25Index.is_current(bm25_image_path(s)))):
            log.info("Building the keyword (BM25) index")
            build_bm25_indexes(s)

    def _build_vector_index(self, reason: str) -> None:
        """Embed data/processed into Qdrant (e.g. a fresh checkout that ships only data/processed)."""
        from rag.index.indexer import Indexer

        log.info("Updating the search index from %s (%s) - this can take a while on a CPU", self.settings.chunks_file, reason)

        def progress(name: str, done: int, total: int) -> None:
            self.index_progress = {"collection": name, "done": done, "total": total}

        Indexer(self.settings, self.embedder, self.store, progress).run(full=reason in Indexer.FULL_REBUILD)

    @property
    def ready(self) -> bool:
        return not self.starting and self.answers is not None and not self.error

    def close(self) -> None:
        if self.store is not None:
            self.store.close()

    # ------------------------------------------------------------ reindex jobs
    def start_reindex(self, full: bool, recrawl: bool) -> Job:
        if self.starting or self.indexing:
            raise RuntimeError("The service is still building its index")
        if not self._job_lock.acquire(blocking=False):
            raise RuntimeError("A reindex job is already running")
        stages = ["crawl", "extract", "images", "chunk", "index"] if recrawl else ["extract", "images", "chunk", "index"]
        job = Job(id=uuid.uuid4().hex[:12], mode="full" if full else "incremental", stages=stages)
        self.jobs[job.id] = job
        thread = threading.Thread(target=self._run_job, args=(job, full), daemon=True, name=f"reindex-{job.id}")
        thread.start()
        return job

    def _run_job(self, job: Job, full: bool) -> None:
        from rag.pipeline import run_pipeline

        job.state, job.started_at = "running", utc_now()
        try:
            if self.embedder is None or self.store is None:
                raise RuntimeError(self.error or "services not initialised")
            job.report = run_pipeline(self.settings, tuple(job.stages), full=full, store=self.store, embedder=self.embedder)
            self.load()
            job.state = "finished"
        except Exception as exc:
            log.exception("Reindex job %s failed", job.id)
            job.state, job.error = "failed", str(exc)
        finally:
            job.finished_at = utc_now()
            self._job_lock.release()

    @property
    def job_running(self) -> bool:
        return self._job_lock.locked()
