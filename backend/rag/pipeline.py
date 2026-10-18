"""Run pipeline stages in order. Shared by the CLI and the admin reindex endpoint."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from rag.config import BACKEND_DIR, Settings
from rag.utils import update_status, utc_now

log = logging.getLogger(__name__)

STAGES = ("crawl", "extract", "images", "chunk", "index")


def run_crawl_subprocess(settings: Settings, urls_file: str | None = None) -> None:
    """Scrapy's reactor can't restart in-process, so crawls always run in a child process."""
    env = dict(os.environ)
    if urls_file:
        env["RAG_CRAWL_URLS_FILE"] = urls_file
    env["DATA_DIR"] = str(settings.data_dir)
    env["CRAWL_START_URLS"] = ",".join(settings.crawl_start_urls)
    env["CRAWL_ALLOWED_DOMAINS"] = ",".join(settings.crawl_allowed_domains)
    env["CRAWL_MAX_PAGES"] = str(settings.crawl_max_pages)
    env["CRAWL_DELAY_SECONDS"] = str(settings.crawl_delay_seconds)
    env["CRAWL_OBEY_ROBOTS"] = str(settings.crawl_obey_robots).lower()
    env["CRAWL_USE_SITEMAPS"] = str(settings.crawl_use_sitemaps).lower()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(BACKEND_DIR), env.get("PYTHONPATH", "")]))
    result = subprocess.run([sys.executable, "-m", "rag.crawler.run"], env=env, cwd=str(BACKEND_DIR))
    if result.returncode != 0:
        update_status(settings.status_file, "crawl", state="failed", finished_at=utc_now())
        raise RuntimeError("Crawl failed or returned no pages; see logs")


def run_pipeline(settings: Settings, stages: tuple[str, ...] = STAGES, full: bool = False, store=None, embedder=None) -> dict:
    from rag.chunking.stage import run_chunking
    from rag.extraction.stage import run_extraction
    from rag.images.stage import run_image_stage

    report: dict = {}
    settings.ensure_dirs()
    for stage in STAGES:
        if stage not in stages:
            continue
        log.info("=== stage: %s ===", stage)
        if stage == "crawl":
            run_crawl_subprocess(settings)
        elif stage == "extract":
            report["documents"] = len(run_extraction(settings))
        elif stage == "images":
            report["images"] = len(run_image_stage(settings))
        elif stage == "chunk":
            report["chunks"] = len(run_chunking(settings))
        elif stage == "index":
            from rag.embeddings import get_embedder
            from rag.index.indexer import Indexer
            from rag.index.qdrant_store import QdrantStore

            own_store = store is None
            store = store or QdrantStore.from_settings(settings)
            try:
                report["index"] = Indexer(settings, embedder or get_embedder(settings), store).run(full=full)
            finally:
                if own_store:
                    store.close()
    return report
