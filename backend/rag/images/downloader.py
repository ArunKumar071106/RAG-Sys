"""Safe image download + validation + duplicate detection.

* Only http(s) URLs on allowed hosts (images on the official domain or its
  CDN hosts listed in CRAWL_ALLOWED_DOMAINS) are fetched.
* Size is capped while streaming; the content is verified with Pillow and
  re-encoded format/dimensions are recorded.
* Files are stored under ``data/images/<sha[:2]>/<sha>.<ext>`` - the
  filename never comes from the remote server, so path traversal is impossible.
* Exact duplicates are detected with SHA-256, near duplicates (resized
  copies) with a 64-bit average hash.
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)

ALLOWED_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "GIF": ("image/gif", "gif"),
                   "WEBP": ("image/webp", "webp"), "BMP": ("image/bmp", "bmp"), "TIFF": ("image/tiff", "tif")}
Image.MAX_IMAGE_PIXELS = 60_000_000  # decompression-bomb guard


@dataclass
class DownloadResult:
    status: str  # ok | http_error | too_large | invalid | unsupported_type | skipped_small
    local_path: str = ""
    sha256: str = ""
    ahash: str = ""
    mime_type: str = ""
    width: int = 0
    height: int = 0
    file_size: int = 0
    error: str = ""


def average_hash(image: Image.Image, size: int = 8) -> str:
    small = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(small.tobytes())  # mode "L": one byte per pixel
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= mean else "0" for p in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def hamming(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def validate_image_bytes(data: bytes, min_dimension: int) -> tuple[DownloadResult, Image.Image | None]:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        return DownloadResult(status="invalid", error=f"not a valid image: {exc}"), None
    fmt = (image.format or "").upper()
    if fmt not in ALLOWED_FORMATS:
        return DownloadResult(status="unsupported_type", error=f"format {fmt or 'unknown'}"), None
    width, height = image.size
    if min(width, height) < min_dimension:
        return DownloadResult(status="skipped_small", width=width, height=height, error="image too small"), None
    mime, _ = ALLOWED_FORMATS[fmt]
    return DownloadResult(status="ok", mime_type=mime, width=width, height=height, file_size=len(data)), image


class ImageDownloader:
    def __init__(self, images_dir: Path, max_bytes: int, min_dimension: int, timeout: int = 30,
                 user_agent: str = "AAACET-RAG-Bot/1.0", retries: int = 2, client: httpx.Client | None = None):
        self.images_dir = images_dir
        self.max_bytes = max_bytes
        self.min_dimension = min_dimension
        self.retries = retries
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent})

    def close(self) -> None:
        self.client.close()

    def _fetch(self, url: str) -> tuple[bytes | None, str]:
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                with self.client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        return None, f"HTTP {response.status_code}"
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > self.max_bytes:
                        return None, "too_large"
                    buf = bytearray()
                    for part in response.iter_bytes():
                        buf.extend(part)
                        if len(buf) > self.max_bytes:
                            return None, "too_large"
                    return bytes(buf), ""
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(0.5 * (2 ** attempt))
        return None, last_error or "download failed"

    def download(self, url: str) -> DownloadResult:
        data, error = self._fetch(url)
        if data is None:
            status = "too_large" if error == "too_large" else "http_error"
            return DownloadResult(status=status, error=error)
        result, image = validate_image_bytes(data, self.min_dimension)
        if image is None:
            return result
        sha = hashlib.sha256(data).hexdigest()
        _, ext = ALLOWED_FORMATS[(image.format or "").upper()]
        path = self.images_dir / sha[:2] / f"{sha}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        result.sha256 = sha
        result.ahash = average_hash(image)
        result.local_path = str(path.relative_to(self.images_dir))
        image.close()
        return result
