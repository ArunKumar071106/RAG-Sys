"""Signing in (name + mobile number, saved to Excel), the admin panel's API, the dashboard, and answers
the admin writes for unanswered questions going through chunking and indexing like website pages."""

import shutil
import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_settings
from rag.admin_answers import AnswerStore, answer_chunks, merge_answer_chunks
from rag.api.app import create_app
from rag.users import InvalidUser, UserStore, clean_name, clean_phone

ADMIN = {"Authorization": "Bearer admin-secret"}


def test_names_and_mobile_numbers_are_checked():
    assert clean_phone("+91 98765-43210") == "9876543210"
    assert clean_phone("09876543210") == "9876543210"
    assert clean_name("  Arun   Kumar ") == "Arun Kumar" and clean_name("அருண் குமார்") == "அருண் குமார்"
    for bad in ("12345", "1234567890", "98765 4321a"):
        with pytest.raises(InvalidUser):
            clean_phone(bad)
    for bad in ("A", "R2D2", "<script>"):
        with pytest.raises(InvalidUser):
            clean_name(bad)


def test_visitors_are_saved_in_excel_and_tokens_cannot_be_made_up(tmp_path):
    from openpyxl import load_workbook

    store = UserStore(tmp_path)
    first = store.register("Arun Kumar", "9876543210")
    again = store.register("Arun K", "+91 98765 43210")  # the same phone: the same visitor
    store.asked(first["user_id"])
    assert first["user_id"] == again["user_id"] and store.verify(first["token"]) == first["user_id"]
    assert store.verify(first["user_id"] + ".0000") is None and store.verify("anything") is None
    rows = list(load_workbook(store.path).active.values)
    assert rows[0][:6] == ("Name", "Phone", "First visit", "Last visit", "Visits", "Questions asked")
    assert rows[1][0] == "Arun K" and rows[1][1] == "9876543210" and rows[1][4] == 2 and rows[1][5] == 1
    assert store.count() == 1


def test_chatting_needs_signing_in(pipeline, services):
    settings = pipeline.settings.model_copy(update={"login_required": True, "data_dir": pipeline.settings.data_dir})
    with TestClient(create_app(settings, services=services)) as client:
        assert client.post("/api/chat", json={"message": "hostel"}).status_code == 401
        bad = client.post("/api/users", json={"name": "Arun", "phone": "12345"})
        assert bad.status_code == 422 and "mobile number" in bad.json()["detail"]
        token = client.post("/api/users", json={"name": "Arun", "phone": "9876543210"}).json()["token"]
        assert client.post("/api/chat", json={"message": "hostel"}, headers={"X-Arivazhai-User": token}).status_code == 200
        assert client.post("/api/chat", json={"message": "hostel"}, headers={"X-Arivazhai-User": "x.y"}).status_code == 401


def test_admin_pages_need_the_admin_password(pipeline, services):
    settings = pipeline.settings.model_copy(update={"admin_token": "admin-secret"})
    with TestClient(create_app(settings, services=services)) as client:
        for path in ("/api/admin/check", "/api/admin/dashboard", "/api/admin/answers", "/api/admin/users.xlsx"):
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/admin/check", headers=ADMIN).json() == {"ok": True}
        # the Excel file and the admin folder are never served as files
        assert client.get("/data/admin/users.xlsx").status_code == 404


def test_dashboard_counts_questions_and_their_times(pipeline, services):
    settings = pipeline.settings.model_copy(update={"admin_token": "admin-secret"})
    with TestClient(create_app(settings, services=services)) as client:
        for question in ("Is there a hostel?", "is there a HOSTEL", "zzqx wvvy plorp"):
            client.post("/api/chat", json={"message": question})
        board = client.get("/api/admin/dashboard", headers=ADMIN).json()
    assert board["totals"]["questions"] >= 3 and board["totals"]["today"] >= 3
    top = {row["key"]: row["count"] for row in board["top_questions"]}
    assert top["is there a hostel"] >= 2
    assert sum(board["by_hour"]) == board["totals"]["questions"] and len(board["daily"]) == 30
    assert board["totals"]["avg_seconds"] is not None and board["timezone"] == "Asia/Kolkata"
    assert any(row["question"] == "zzqx wvvy plorp" and not row["answered"] for row in board["unanswered"])


def test_admin_answers_are_chunked_like_pages(settings):
    store = AnswerStore(settings.data_dir / "admin")
    entry = store.save("Is there a canteen?", "Yes. The canteen is open 8 AM to 6 PM.\n\nIt serves lunch.",
                       resolves=["is there a canteen on campus"])
    chunks = answer_chunks(settings)
    assert len(chunks) == 1 and chunks[0].doc_id == "admin-" + entry["id"]
    assert chunks[0].url == f"/api/answers/{entry['id']}" and "8 AM to 6 PM" in chunks[0].text
    assert "Is there a canteen?" in chunks[0].embedding_text()
    assert store.resolved_keys() == {"is there a canteen", "is there a canteen on campus"}
    assert merge_answer_chunks(settings) == 1 and merge_answer_chunks(settings) == 1  # replaced, never doubled


def test_an_admin_answer_is_found_by_the_next_visitor(pipeline, tmp_path):
    from rag.api.services import Services
    from rag.embeddings.base import HashingEmbedder

    # a copy of the demo knowledge base, so the shared one stays as it is
    settings = make_settings(tmp_path / "data", admin_token="admin-secret")
    shutil.copytree(pipeline.settings.processed_dir, settings.processed_dir)
    services = Services(settings, embedder=HashingEmbedder(settings.hashing_dim), load_llm=False)
    try:
        with TestClient(create_app(settings, services=services)) as client:
            question = "Does the college run a summer coding camp for school students?"
            before = client.post("/api/chat", json={"message": question}).json()
            saved = client.post("/api/admin/answers", headers=ADMIN, json={
                "question": question, "resolves": [question],
                "answer": "Yes. The summer coding camp for school students runs every May for two weeks."}).json()
            answer_id, job = saved["answer"]["id"], saved["indexing"]
            for _ in range(100):
                if client.get(f"/api/admin/jobs/{job}", headers=ADMIN).json()["state"] in ("finished", "failed"):
                    break
                time.sleep(0.1)
            assert client.get(f"/api/admin/jobs/{job}", headers=ADMIN).json()["state"] == "finished"
            after = client.post("/api/chat", json={"message": "summer coding camp for school students"}).json()
            assert f"/api/answers/{answer_id}" in [s["url"] for s in after["sources"]]
            assert "every May" in after["answer"] and before["mode"] != after["mode"] or "every May" in after["answer"]
            page = client.get(f"/api/answers/{answer_id}")
            assert page.status_code == 200 and "every May" in page.text and "admission office" in page.text
            board = client.get("/api/admin/dashboard", headers=ADMIN).json()
            assert all(row["answered"] for row in board["unanswered"] if row["key"] == question.lower().rstrip("?"))
            # deleting it takes it out of the index again
            client.delete(f"/api/admin/answers/{answer_id}", headers=ADMIN)
            assert client.get(f"/api/answers/{answer_id}").status_code == 404
    finally:
        services.close()
