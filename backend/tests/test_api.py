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


def test_not_ready_service_returns_503(tmp_path):
    settings = make_settings(tmp_path / "data", embedding_provider="bge-m3", embedding_model="/nonexistent/model")
    services = Services(settings, load_llm=False)  # bge-m3 unavailable -> degraded, not crashed
    app = create_app(settings, services=services)
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "degraded"
        response = c.post("/api/chat", json={"message": "hello there"})
        assert response.status_code == 503 and "not ready" in response.json()["detail"]
    services.close()
