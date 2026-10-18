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

    def __init__(self, settings: Settings, embedder=None, store=None, llm=None, load_llm: bool = True):
        self.settings = settings
        self.embedder = embedder
        self.store = store
        self.llm = llm
        self._load_llm = load_llm and llm is None
        self.corpus = None
        self.retriever = None
        self.answers = None
        self.error = ""
        self.jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._job_lock = threading.Lock()
        self.load()

    # ------------------------------------------------------------ lifecycle
    def load(self) -> None:
        from rag.embeddings import get_embedder
        from rag.index.bm25 import BM25Index
        from rag.index.indexer import bm25_image_path, bm25_text_path
        from rag.index.qdrant_store import QdrantStore
        from rag.llm.answer import AnswerService
        from rag.llm.client import get_llm
        from rag.retrieval.corpus import Corpus
        from rag.retrieval.hybrid import HybridRetriever, Reranker

        with self._lock:
            try:
                if self.embedder is None:
                    self.embedder = get_embedder(self.settings)
                if self.store is None:
                    self.store = QdrantStore.from_settings(self.settings)
                if self._load_llm:
                    self.llm = get_llm(self.settings)
                    self._load_llm = False
                self.corpus = Corpus.load(self.settings)
                reranker = None
                if self.settings.rerank_enabled:
                    try:
                        reranker = Reranker(self.settings.rerank_model)
                    except Exception as exc:
                        log.warning("Reranker unavailable: %s", exc)
                self.retriever = HybridRetriever(
                    self.settings, self.embedder, self.store, self.corpus,
                    BM25Index.load(bm25_text_path(self.settings)), BM25Index.load(bm25_image_path(self.settings)), reranker,
                )
                self.answers = AnswerService(self.retriever, self.llm, self.settings.llm_history_turns,
                                             self.settings.retrieval_top_k, self.settings.image_top_k)
                self.error = ""
            except Exception as exc:
                log.exception("Failed to load RAG services")
                self.error = f"{type(exc).__name__}: {exc}"

    @property
    def ready(self) -> bool:
        return self.answers is not None and not self.error

    def close(self) -> None:
        if self.store is not None:
            self.store.close()

    # ------------------------------------------------------------ reindex jobs
    def start_reindex(self, full: bool, recrawl: bool) -> Job:
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
