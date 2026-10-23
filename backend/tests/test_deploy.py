import sys

from rag.config import PROJECT_DIR

sys.path.insert(0, str(PROJECT_DIR / "scripts"))
from deploy_hf_space import space_url, stage  # noqa: E402


def test_space_gets_the_dockerfile_code_and_knowledge_base_but_no_secrets(tmp_path):
    files = stage(tmp_path)
    assert {"Dockerfile", "README.md", "backend/requirements.txt", "backend/rag/api/app.py",
            "data/processed/chunks.jsonl", "data/status.json"} <= set(files)
    assert not any("__pycache__" in f or f.endswith(".env") or "tests/" in f for f in files)
    assert "sdk: docker" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "7860" in (tmp_path / "Dockerfile").read_text(encoding="utf-8")


def test_space_url():
    assert space_url("ArunKumar071106/arivazhai-api") == "https://arunkumar071106-arivazhai-api.hf.space"
