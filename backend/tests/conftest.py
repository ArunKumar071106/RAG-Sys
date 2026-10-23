"""Shared fixtures.

The session-scoped ``pipeline`` fixture builds the FICTIONAL demo site,
serves it on localhost, runs the real crawler (subprocess), extraction,
image processing (download, validation, OCR), chunking and indexing into an
embedded Qdrant, once for the whole test run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from rag.config import Settings
from rag.demo.site import build_demo_site, serve_directory
from rag.embeddings.base import HashingEmbedder
from rag.index.qdrant_store import QdrantStore


def make_settings(data_dir: Path, **overrides) -> Settings:
    values = dict(
        data_dir=data_dir,
        embedding_provider="hashing",
        llm_provider="extractive",
        vision_enabled=False,
        crawl_delay_seconds=0.0,
        crawl_allowed_domains=["127.0.0.1"],
        cors_origins=["http://localhost:5173"],
        admin_token="",
        rate_limit_per_minute=0,
        qdrant_url="",  # never a real server, whatever the shell exports
        qdrant_api_key="",
        qdrant_path=None,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path / "data")


@dataclass
class Pipeline:
    settings: Settings
    store: QdrantStore
    embedder: HashingEmbedder
    base_url: str
    report: dict


@pytest.fixture(scope="session")
def demo_site(tmp_path_factory):
    root = build_demo_site(tmp_path_factory.mktemp("site"))
    server, base = serve_directory(root)
    yield root, base
    server.shutdown()


@pytest.fixture(scope="session")
def pipeline(demo_site, tmp_path_factory) -> Pipeline:
    from rag.pipeline import run_pipeline

    _, base = demo_site
    settings = make_settings(tmp_path_factory.mktemp("pipeline") / "data", crawl_start_urls=[base + "/"])
    store = QdrantStore.from_settings(settings)
    embedder = HashingEmbedder(settings.hashing_dim)
    report = run_pipeline(settings, full=True, store=store, embedder=embedder)
    yield Pipeline(settings, store, embedder, base, report)
    store.close()


@pytest.fixture(scope="session")
def services(pipeline):
    from rag.api.services import Services

    return Services(pipeline.settings, embedder=pipeline.embedder, store=pipeline.store, load_llm=False)
