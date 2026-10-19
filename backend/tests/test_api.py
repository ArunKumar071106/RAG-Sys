import time

import pytest
from fastapi.testclient import TestClient

from rag.api.app import create_app
from rag.api.services import Services
from rag.models import ImageRecord, TextChunk
from rag.utils import read_jsonl
from tests.conftest import make_settings


@pytest.fixture
def client(pipeline, services):
    app = create_app(pipeline.settings.model_copy(update={"rate_limit_per_minute": 0}), services=services)
    with TestClient(app) as c:
        yield c


def test_health_reports_components(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok" and data["ready"] and data["indexed"]
    assert data["components"]["embedder"].startswith("hashing") and data["components"]["llm"] == "extractive"
    assert data["counts"]["text_points"] > 0 and data["counts"]["image_points"] > 0


def test_status_reports_stages(client):
    data = client.get("/api/status").json()
    assert {"crawl", "extract", "images", "chunk", "index"} <= set(data["stages"])
    assert data["index"]["embedder"].startswith("hashing") and data["reindex_running"] is False


def test_chat_returns_grounded_answer_sources_and_images(client):
    response = client.post("/api/chat", json={"message": "Show me the admission notice poster"})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "extractive" and not data["insufficient_evidence"]
    assert data["sources"][0]["url"].endswith("/admissions.html")
    poster = next(i for i in data["images"] if i["original_url"].endswith("admission-notice.png"))
    file = client.get(poster["src"])
    assert file.status_code == 200 and file.headers["content-type"] == "image/png"
    assert file.headers["x-content-type-options"] == "nosniff"


def test_chat_no_answer(client):
    data = client.post("/api/chat", json={"message": "zzqx wvvy plorp"}).json()
    assert data["mode"] == "no_answer" and data["insufficient_evidence"] and data["sources"] == []


@pytest.mark.parametrize("payload, status", [
    ({"message": ""}, 422),
    ({"message": "   "}, 422),
    ({}, 422),
    ({"message": "x" * 5000}, 422),
    ({"message": "hi", "history": [{"role": "system", "content": "x"}]}, 422),
])
def test_chat_input_validation(client, payload, status):
    assert client.post("/api/chat", json=payload).status_code == status


def test_body_size_limit(client):
    response = client.post("/api/chat", content=b"{" + b" " * 200_000 + b"}", headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_search_endpoints(client):
    text = client.post("/api/search/text", json={"query": "hostel capacity", "top_k": 3}).json()
    assert text and text[0]["url"].endswith("facilities.html") and "semantic_rank" in text[0]
    images = client.post("/api/search/images", json={"query": "boys hostel block", "top_k": 2}).json()
    assert images[0]["url"].endswith("hostel-block.jpg")
    assert client.post("/api/search/text", json={"query": "x", "top_k": 99}).status_code == 422


def test_source_and_image_metadata(client, pipeline):
    chunk = next(read_jsonl(pipeline.settings.chunks_file, TextChunk))
    assert client.get(f"/api/sources/{chunk.chunk_id}").json()["text"] == chunk.text
    assert client.get("/api/sources/does-not-exist").status_code == 404
    record = next(r for r in read_jsonl(pipeline.settings.images_file, ImageRecord) if r.status == "ok")
    meta = client.get(f"/api/images/{record.image_id}").json()
    assert meta["url"] == record.url and "local_path" not in meta
    broken = next(r for r in read_jsonl(pipeline.settings.images_file, ImageRecord) if r.status == "http_error")
    assert client.get(f"/api/images/{broken.image_id}/file").status_code == 404
    assert client.get("/api/images/..%2F..%2Fstatus.json/file").status_code == 404


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/api/chat", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limit(pipeline, services):
    app = create_app(pipeline.settings.model_copy(update={"rate_limit_per_minute": 2}), services=services)
    with TestClient(app) as c:
        codes = [c.post("/api/search/text", json={"query": "hostel"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_admin_requires_token(pipeline, services):
    app = create_app(pipeline.settings, services=services)  # admin_token empty
    with TestClient(app) as c:
        assert c.post("/api/admin/reindex", json={}).status_code == 503


def test_admin_reindex_job(pipeline, services):
    app = create_app(pipeline.settings.model_copy(update={"admin_token": "s3cret"}), services=services)
    with TestClient(app) as c:
        assert c.post("/api/admin/reindex", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.post("/api/admin/reindex", json={}).status_code == 401
        auth = {"Authorization": "Bearer s3cret"}
        response = c.post("/api/admin/reindex", json={"recrawl": False, "full": False}, headers=auth)
        assert response.status_code == 202
        job_id = response.json()["id"]
        for _ in range(100):
            job = c.get(f"/api/admin/jobs/{job_id}", headers=auth).json()
            if job["state"] in ("finished", "failed"):
                break
            time.sleep(0.1)
        assert job["state"] == "finished", job
        assert job["report"]["index"]["text"]["upserted"] == 0  # nothing changed -> incremental no-op
        assert c.get("/api/admin/jobs/nope", headers=auth).status_code == 404
        assert c.post("/api/chat", json={"message": "library timings"}).status_code == 200


def test_not_ready_service_returns_503(tmp_path, monkeypatch):
    import rag.embeddings.base as emb

    def broken_model(*args, **kwargs):
        raise OSError("model /nonexistent/model not found")

    monkeypatch.setattr(emb, "BgeM3Embedder", broken_model)
    settings = make_settings(tmp_path / "data", embedding_provider="bge-m3", embedding_model="/nonexistent/model")
    services = Services(settings, load_llm=False)  # model fails to load -> degraded, not crashed
    app = create_app(settings, services=services)
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "degraded"
        response = c.post("/api/chat", json={"message": "hello there"})
        assert response.status_code == 503 and "not ready" in response.json()["detail"]
    services.close()


def test_api_builds_missing_index_on_startup(pipeline, tmp_path):
    """A checkout that ships only data/processed must work without running the pipeline."""
    import shutil

    from rag.embeddings.base import HashingEmbedder

    settings = make_settings(tmp_path / "data")
    settings.ensure_dirs()
    for name in ("chunks.jsonl", "image_chunks.jsonl", "images.jsonl"):
        shutil.copy(pipeline.settings.processed_dir / name, settings.processed_dir / name)
    services = Services(settings, embedder=HashingEmbedder(settings.hashing_dim), load_llm=False)
    try:
        assert services.ready, services.error
        assert services.store.count(settings.qdrant_text_collection) == len(services.corpus.chunks) > 0
        app = create_app(settings, services=services)
        with TestClient(app) as c:
            data = c.post("/api/chat", json={"message": "What is the tuition fee for B.Tech Data Science?"}).json()
        assert data["mode"] == "extractive" and "60,000" in data["answer"]
    finally:
        services.close()


def test_api_answers_with_keyword_search_while_building_index_in_background(pipeline, tmp_path):
    """A first start can spend a long time embedding on a CPU; questions are answered meanwhile."""
    import shutil
    import threading
    import time

    from rag.embeddings.base import HashingEmbedder

    class GatedEmbedder(HashingEmbedder):
        def __init__(self, dim):
            super().__init__(dim)
            self.release = threading.Event()

        def embed_documents(self, texts):
            self.release.wait(10)
            return super().embed_documents(texts)

    settings = make_settings(tmp_path / "data")
    settings.ensure_dirs()
    for name in ("chunks.jsonl", "image_chunks.jsonl", "images.jsonl"):
        shutil.copy(pipeline.settings.processed_dir / name, settings.processed_dir / name)
    embedder = GatedEmbedder(settings.hashing_dim)
    services = Services(settings, embedder=embedder, load_llm=False, background=True)
    question = {"message": "What is the tuition fee for B.Tech Data Science?"}
    try:
        app = create_app(settings, services=services)
        with TestClient(app) as c:
            deadline = time.monotonic() + 10
            while not services.indexing and time.monotonic() < deadline:
                time.sleep(0.02)
            health = c.get("/api/health").json()
            assert health["status"] == "indexing" and health["ready"] and health["search"] == "keyword"
            assert "60,000" in c.post("/api/chat", json=question).json()["answer"]
            assert services.retriever.semantic_enabled is False
            embedder.release.set()
            deadline = time.monotonic() + 30
            while services.indexing and time.monotonic() < deadline:
                time.sleep(0.05)
            health = c.get("/api/health").json()
            assert health["status"] == "ok" and health["search"] == "hybrid", health
            result = c.post("/api/chat", json=question).json()
            assert "60,000" in result["answer"] and services.retriever.semantic_enabled
    finally:
        embedder.release.set()
        services.close()


def test_api_answers_starting_up_while_the_model_loads(tmp_path, monkeypatch):
    import threading

    import rag.embeddings as embeddings
    from rag.embeddings.base import HashingEmbedder

    release = threading.Event()

    def slow_model(settings):
        release.wait(10)
        return HashingEmbedder(settings.hashing_dim)

    monkeypatch.setattr(embeddings, "get_embedder", slow_model)
    settings = make_settings(tmp_path / "data")
    services = Services(settings, load_llm=False, background=True)
    try:
        app = create_app(settings, services=services)
        with TestClient(app) as c:
            assert c.get("/api/health").json()["status"] == "starting"
            response = c.post("/api/chat", json={"message": "hello there"})
            assert response.status_code == 503 and response.headers["Retry-After"] == "30"
            assert "starting up" in response.json()["detail"]
    finally:
        release.set()


def test_interrupted_index_build_resumes(pipeline, tmp_path):
    import shutil

    from rag.embeddings.base import HashingEmbedder
    from rag.index.indexer import Indexer
    from rag.index.qdrant_store import QdrantStore

    settings = make_settings(tmp_path / "data")
    settings.ensure_dirs()
    for name in ("chunks.jsonl", "image_chunks.jsonl", "images.jsonl"):
        shutil.copy(pipeline.settings.processed_dir / name, settings.processed_dir / name)
    embedder = HashingEmbedder(settings.hashing_dim)
    store = QdrantStore.from_settings(settings)
    try:
        class Stop(Exception):
            pass

        def stop_after_first_batch(name, done, total):
            raise Stop

        with pytest.raises(Stop):
            Indexer(settings, embedder, store, stop_after_first_batch).run(full=True)
        assert Indexer.build_needed(settings, embedder, store) == "an interrupted build"
        stored = store.count(settings.qdrant_text_collection)
        assert stored > 0

        embedded: list[int] = []
        original = embedder.embed_documents
        embedder.embed_documents = lambda texts: (embedded.append(len(texts)), original(texts))[1]
        report = Indexer(settings, embedder, store).run()
        assert report["validation"]["ok"] and Indexer.build_needed(settings, embedder, store) == ""
        total = report["text"]["upserted"] + report["images"]["upserted"]
        assert sum(embedded) == total - stored  # only what the interrupted run had not stored
    finally:
        store.close()


def test_keyword_index_from_an_older_tokenizer_is_rebuilt(pipeline, tmp_path):
    import json
    import shutil

    from rag.embeddings.base import HashingEmbedder
    from rag.index.bm25 import BM25Index
    from rag.index.indexer import bm25_text_path

    settings = make_settings(tmp_path / "data")
    settings.ensure_dirs()
    for name in ("chunks.jsonl", "image_chunks.jsonl", "images.jsonl"):
        shutil.copy(pipeline.settings.processed_dir / name, settings.processed_dir / name)
    embedder = HashingEmbedder(settings.hashing_dim)
    Services(settings, embedder=embedder, load_llm=False).close()
    path = bm25_text_path(settings)
    old = json.loads(path.read_text(encoding="utf-8"))
    del old["tokenizer"]  # as written before tokenizer versions existed
    path.write_text(json.dumps(old), encoding="utf-8")
    assert not BM25Index.is_current(path)
    services = Services(settings, embedder=embedder, load_llm=False)
    try:
        assert services.ready, services.error
        assert BM25Index.is_current(path)
    finally:
        services.close()


def test_updated_knowledge_base_is_reindexed_incrementally(pipeline, tmp_path):
    """After a pull that changes data/processed, the next start re-embeds only what changed."""
    import json
    import shutil

    from rag.embeddings.base import HashingEmbedder
    from rag.index.indexer import Indexer

    settings = make_settings(tmp_path / "data")
    settings.ensure_dirs()
    for name in ("chunks.jsonl", "image_chunks.jsonl", "images.jsonl"):
        shutil.copy(pipeline.settings.processed_dir / name, settings.processed_dir / name)
    embedder = HashingEmbedder(settings.hashing_dim)
    Services(settings, embedder=embedder, load_llm=False).close()

    lines = settings.chunks_file.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["page_title"] = "Retitled page"
    settings.chunks_file.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n", encoding="utf-8")

    from rag.index.qdrant_store import QdrantStore
    store = QdrantStore.from_settings(settings)
    try:
        assert Indexer.build_needed(settings, embedder, store) == "the knowledge base changed"
        report = Indexer(settings, embedder, store).run()
        assert report["mode"] == "incremental" and report["text"]["changed_documents"] == 1
        assert Indexer.build_needed(settings, embedder, store) == ""
    finally:
        store.close()

