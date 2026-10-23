"""Deploy the backend to a Hugging Face Space (Docker), using the vectors already in Qdrant Cloud.

    python scripts/deploy_hf_space.py --space <hf-username>/arivazhai-api --cors https://<site>.netlify.app
    python scripts/deploy_hf_space.py --space <hf-username>/arivazhai-api --dry-run   # list what would be uploaded

What it does:
1. checks .env points at a Qdrant server or Qdrant Cloud and the cluster holds the vectors and the index record
   (so the Space starts in seconds instead of embedding and uploading everything again);
2. creates the Space (Docker SDK, public: the frontend calls it from visitors' browsers) if it does not exist;
3. uploads deploy/huggingface/{Dockerfile,README.md} to its root, backend/rag, backend/requirements.txt and the
   knowledge base (data/processed/*.jsonl, data/status.json) in one commit, which makes the Space build;
4. stores QDRANT_URL, QDRANT_API_KEY (and ANTHROPIC_API_KEY if set) as Space secrets and CORS_ORIGINS as a variable.
   Keys are never written into the uploaded files.

Needs a Hugging Face access token with write permission: --token, the HF_TOKEN environment variable, an earlier
`hf auth login`, or the prompt.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

KNOWLEDGE_BASE = ["data/processed/chunks.jsonl", "data/processed/image_chunks.jsonl",
                  "data/processed/images.jsonl", "data/status.json"]


def space_url(space: str) -> str:
    """'ArunKumar/arivazhai-api' -> 'https://arunkumar-arivazhai-api.hf.space'."""
    return "https://" + re.sub(r"[^a-z0-9]+", "-", space.lower()).strip("-") + ".hf.space"


def stage(target: Path) -> list[str]:
    """Copy what the Space needs into target, laid out as the Dockerfile expects."""
    files: list[str] = []

    def put(source: Path, relative: str) -> None:
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        files.append(relative)

    put(ROOT / "deploy" / "huggingface" / "Dockerfile", "Dockerfile")
    put(ROOT / "deploy" / "huggingface" / "README.md", "README.md")
    put(ROOT / "backend" / "requirements.txt", "backend/requirements.txt")
    for source in sorted((ROOT / "backend" / "rag").rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
            put(source, "backend/" + source.relative_to(ROOT / "backend").as_posix())
    for relative in KNOWLEDGE_BASE:
        source = ROOT / relative
        if not source.exists():
            sys.exit(f"Missing {source}: the knowledge base must be in data/processed (it comes with the project).")
        put(source, relative)
    return files


def check_qdrant(settings) -> None:
    from rag.index.indexer import _count_lines, meta_collection
    from rag.index.qdrant_store import QdrantStore

    if not settings.qdrant_url:
        sys.exit("QDRANT_URL is empty in .env: the Space needs the vectors in Qdrant Cloud. "
                 "Set QDRANT_URL and QDRANT_API_KEY, then run: python -m rag.cli check-qdrant")
    store = QdrantStore.from_settings(settings)
    try:
        have = store.count(settings.qdrant_text_collection)
        record = store.load_meta(meta_collection(settings), "manifest")
    except Exception as exc:
        sys.exit(f"Cannot use the Qdrant cluster ({type(exc).__name__}: {exc}). Run: python -m rag.cli check-qdrant")
    finally:
        store.close()
    want = _count_lines(settings.chunks_file)
    if have < want or not record:
        sys.exit(f"The cluster holds {have} of {want} text vectors{'' if record else ' and no index record'}. "
                 "From backend/, run: python -m rag.cli index   then run this script again.")
    print(f"Qdrant: {have} text vectors and the index record are in the cluster.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--space", required=True, help="<hf-username>/<space-name>, e.g. arunkumar/arivazhai-api")
    parser.add_argument("--cors", default="", help="the frontend's address, e.g. https://arivazhai.netlify.app")
    parser.add_argument("--token", default="", help="Hugging Face access token with write permission")
    parser.add_argument("--dry-run", action="store_true", help="only list the files that would be uploaded")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.space):
        parser.error("--space must look like <hf-username>/<space-name>")

    from rag.config import get_settings

    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        files = stage(Path(tmp))
        size = sum((Path(tmp) / f).stat().st_size for f in files) / 1e6
        print(f"{len(files)} files, {size:.1f} MB: Dockerfile, README.md, backend/rag, backend/requirements.txt, "
              "data/processed, data/status.json")
        if args.dry_run:
            print("\n".join(f"  {f}" for f in files))
            return 0
        check_qdrant(settings)

        from huggingface_hub import HfApi, get_token

        token = args.token or os.environ.get("HF_TOKEN") or get_token() or getpass.getpass(
            "Hugging Face token (write permission, from https://huggingface.co/settings/tokens): ").strip()
        api = HfApi(token=token)
        try:
            user = api.whoami()["name"]
        except Exception as exc:
            sys.exit(f"The token was not accepted ({_reason(exc)}). Create a token of type Write at "
                     "https://huggingface.co/settings/tokens and try again.")
        if args.space.split("/")[0].lower() != user.lower():
            print(f"Note: the token belongs to {user!r}; the Space is created under {args.space.split('/')[0]!r}.")
        _step("creating the Space", lambda: api.create_repo(args.space, repo_type="space", space_sdk="docker",
                                                            exist_ok=True))
        print(f"Space: https://huggingface.co/spaces/{args.space}")

        # secrets before the upload, so the first build starts with them
        secrets = {"QDRANT_URL": settings.qdrant_url, "QDRANT_API_KEY": settings.qdrant_api_key,
                   "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY") or _env_file_value("ANTHROPIC_API_KEY")}
        for key, value in secrets.items():
            if value:
                _step(f"storing the secret {key}", lambda k=key, v=value: api.add_space_secret(args.space, k, v))
                print(f"  secret {key} set")
        if args.cors:
            cors = args.cors.rstrip("/")
            _step("storing CORS_ORIGINS", lambda: api.add_space_variable(args.space, "CORS_ORIGINS", cors))
            print(f"  variable CORS_ORIGINS = {cors}")

        _step("uploading the files", lambda: api.upload_folder(
            folder_path=tmp, repo_id=args.space, repo_type="space", commit_message="Deploy the Arivazhai backend",
            delete_patterns=["backend/**", "data/**"]))
    url = space_url(args.space)
    print(f"\nUploaded. The Space builds now (about 5-10 minutes the first time): https://huggingface.co/spaces/{args.space}")
    print(f"Then check {url}/api/health  - and set VITE_API_BASE_URL={url} on Netlify.")
    return 0


def _reason(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    detail = getattr(exc, "server_message", "") or (getattr(response, "text", "") or "")[:300]
    status = getattr(response, "status_code", "")
    return " ".join(str(x) for x in (type(exc).__name__, status, detail.strip() or exc) if x)


def _step(what: str, action):
    try:
        return action()
    except Exception as exc:
        sys.exit(f"Failed while {what}: {_reason(exc)}\n"
                 "Check that the token is of type Write and belongs to the account in --space.")


def _env_file_value(key: str) -> str:
    for path in (ROOT / ".env", ROOT / "backend" / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                name, _, value = line.partition("=")
                if name.strip() == key:
                    return value.split(" #")[0].strip().strip('"').strip("'")
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
