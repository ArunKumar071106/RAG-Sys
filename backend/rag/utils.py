"""Small shared helpers: hashing, URL normalisation, JSONL I/O, text cleanup."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unicodedata
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
_WS_RE = re.compile(r"[ \t\r\f\v ]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_id(*parts: str, length: int = 16) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_url(url: str, base: str | None = None) -> str:
    """Absolute URL without fragment, tracking params or trailing-slash noise."""
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS)
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower().split(":")[0]


def is_allowed_host(url: str, allowed_domains: Iterable[str]) -> bool:
    host = host_of(url)
    for domain in allowed_domains:
        domain = domain.lower().split(":")[0]
        if host == domain or host.endswith("." + domain):
            return True
    return False


def clean_text(text: str) -> str:
    """Normalise unicode and whitespace while keeping paragraph breaks."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("​", "")
    lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return _MULTI_NL_RE.sub("\n\n", text).strip()


def write_jsonl(path: Path, items: Iterable[BaseModel | dict]) -> int:
    """Atomically write items to a JSONL file. Returns the number written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as tmp:
        for item in items:
            data = item.model_dump() if isinstance(item, BaseModel) else item
            tmp.write(json.dumps(data, ensure_ascii=False) + "\n")
            count += 1
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    return count


def read_jsonl(path: Path, model: type[T]) -> Iterator[T]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield model.model_validate_json(line)


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return dict(default or {})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default or {})


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def update_status(status_file: Path, stage: str, **fields: object) -> None:
    """Record progress of a pipeline stage for the /api/status endpoint."""
    status = read_json(status_file)
    entry = status.get(stage, {})
    entry.update(fields)
    entry["updated_at"] = utc_now()
    status[stage] = entry
    write_json(status_file, status)
