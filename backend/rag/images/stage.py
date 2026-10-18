"""Image stage: collect image refs -> download/validate/dedupe -> OCR -> describe -> chunk."""

from __future__ import annotations

import dataclasses
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rag.config import Settings
from rag.images.downloader import DownloadResult, ImageDownloader, hamming
from rag.images.image_chunker import build_image_chunk, extract_keywords, has_searchable_evidence
from rag.images.ocr import get_ocr_engine
from rag.images.vision import get_vision_describer
from rag.models import ImageRecord, ImageRef, PageDocument
from rag.utils import is_allowed_host, read_jsonl, short_id, update_status, write_jsonl

log = logging.getLogger(__name__)


def collect_image_refs(docs: list[PageDocument], allowed_hosts: list[str]) -> tuple[list[ImageRef], dict[str, list[str]]]:
    """Unique image refs (first occurrence wins) and every page each image appears on."""
    refs: dict[str, ImageRef] = {}
    pages: dict[str, list[str]] = {}
    for doc in docs:
        for ref in doc.images:
            if not is_allowed_host(ref.url, allowed_hosts):
                continue
            pages.setdefault(ref.url, [])
            if doc.url not in pages[ref.url]:
                pages[ref.url].append(doc.url)
            existing = refs.get(ref.url)
            if existing is None:
                refs[ref.url] = ref
            elif not existing.alt and ref.alt:
                refs[ref.url] = ref  # prefer the occurrence with the richest metadata
    return list(refs.values()), pages


def _record_from_ref(ref: ImageRef, pages: list[str]) -> ImageRecord:
    context = " ".join(filter(None, [ref.context_before, ref.context_after]))
    return ImageRecord(
        image_id=short_id("img", ref.url),
        url=ref.url,
        alt=ref.alt,
        title=ref.title,
        caption=ref.caption,
        filename=ref.filename,
        source_page=ref.source_page,
        page_title=ref.page_title,
        heading=ref.heading_path[-1] if ref.heading_path else "",
        heading_path=ref.heading_path,
        context=context[:600],
        also_on_pages=[p for p in pages if p != ref.source_page],
    )


def run_image_stage(settings: Settings, downloader: ImageDownloader | None = None) -> list[ImageRecord]:
    settings.ensure_dirs()
    docs = list(read_jsonl(settings.documents_file, PageDocument))
    allowed = settings.crawl_allowed_domains + settings.image_allowed_domains
    refs, pages = collect_image_refs(docs, allowed)
    refs = refs[: settings.image_max_count]
    html_pages = sum(1 for d in docs if d.content_type == "text/html")

    # Reuse previous results for unchanged URLs (incremental runs).
    previous = {r.url: r for r in read_jsonl(settings.images_file, ImageRecord)}

    own_downloader = downloader is None
    downloader = downloader or ImageDownloader(
        settings.images_dir, settings.image_max_bytes, settings.image_min_dimension,
        settings.image_download_timeout, settings.crawl_user_agent,
    )
    ocr = get_ocr_engine(settings.ocr_engine, settings.ocr_min_confidence)
    vision = get_vision_describer(settings.vision_enabled, settings.vision_model)
    described = 0

    def reusable(prev: ImageRecord | None) -> bool:
        return bool(prev and prev.status == "ok" and prev.local_path and (settings.images_dir / prev.local_path).exists())

    # Downloads are network-bound: fetch in a few parallel workers, then process in order.
    # Each result is appended to a journal as it completes, so an interrupted run resumes
    # instead of downloading everything again.
    journal = settings.processed_dir / "image_downloads.jsonl"
    fetched: dict[str, DownloadResult] = {}
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                result = DownloadResult(**row["result"])
            except (ValueError, KeyError, TypeError):
                continue
            if result.status != "ok" or (settings.images_dir / result.local_path).exists():
                fetched[row["url"]] = result
    to_fetch = [r.url for r in refs if not reusable(previous.get(r.url)) and r.url not in fetched]
    if to_fetch:
        log.info("Downloading %d images with %d workers (%d already done)", len(to_fetch),
                 settings.image_download_workers, len(fetched))
        with ThreadPoolExecutor(max_workers=settings.image_download_workers) as pool, \
                journal.open("a", encoding="utf-8") as jf:
            for i, (url, result) in enumerate(zip(to_fetch, pool.map(downloader.download, to_fetch)), start=1):
                fetched[url] = result
                jf.write(json.dumps({"url": url, "result": dataclasses.asdict(result)}) + "\n")
                if i % 100 == 0:
                    jf.flush()
                    log.info("Downloaded %d/%d images", i, len(to_fetch))

    records: list[ImageRecord] = []
    by_sha: dict[str, ImageRecord] = {}
    ok_records: list[ImageRecord] = []
    try:
        for ref in refs:
            record = _record_from_ref(ref, pages.get(ref.url, []))
            prev = previous.get(ref.url)
            local_ok = reusable(prev)
            if local_ok:
                for field in ("local_path", "sha256", "ahash", "mime_type", "width", "height", "file_size",
                              "ocr_text", "ocr_confidence", "description", "description_model"):
                    setattr(record, field, getattr(prev, field))
            else:
                result = fetched.get(ref.url) or downloader.download(ref.url)
                record.status = result.status  # type: ignore[assignment]
                record.error = result.error
                for field in ("local_path", "sha256", "ahash", "mime_type", "width", "height", "file_size"):
                    setattr(record, field, getattr(result, field))
                if result.status != "ok":
                    records.append(record)
                    continue

            # boilerplate: logos/icons repeated on most pages
            occurrences = 1 + len(record.also_on_pages)
            if html_pages >= 3 and occurrences >= max(3, html_pages * settings.boilerplate_page_ratio):
                record.status = "boilerplate"
                records.append(record)
                continue

            # exact and near duplicates
            dup = by_sha.get(record.sha256)
            if dup is None:
                dup = next((r for r in ok_records if hamming(r.ahash, record.ahash) <= 3
                            and abs(r.width / max(r.height, 1) - record.width / max(record.height, 1)) < 0.05), None)
            if dup is not None:
                record.status = "duplicate"
                record.duplicate_of = dup.image_id
                if record.source_page not in dup.also_on_pages and record.source_page != dup.source_page:
                    dup.also_on_pages.append(record.source_page)
                for field in ("alt", "caption", "title"):
                    if not getattr(dup, field) and getattr(record, field):
                        setattr(dup, field, getattr(record, field))
                records.append(record)
                continue

            path = settings.images_dir / record.local_path
            if not local_ok:
                try:
                    result_ocr = ocr.read(path)
                    record.ocr_text, record.ocr_confidence = result_ocr.text, result_ocr.confidence
                except Exception as exc:
                    log.warning("OCR failed for %s: %s", ref.url, exc)
            if vision and not record.description and described < settings.vision_max_images:
                record.description = vision.describe(path, record.mime_type, record.context)
                record.description_model = settings.vision_model if record.description else ""
                described += 1
            record.status = "ok"
            by_sha[record.sha256] = record
            ok_records.append(record)
            records.append(record)
    finally:
        if own_downloader:
            downloader.close()

    for record in ok_records:
        record.keywords = extract_keywords(record)
    chunks = [build_image_chunk(r) for r in ok_records if has_searchable_evidence(r)]
    write_jsonl(settings.images_file, records)
    write_jsonl(settings.image_chunks_file, chunks)

    counts: dict[str, int] = {}
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
    update_status(settings.status_file, "images", total=len(records), chunks=len(chunks), ocr_engine=ocr.name,
                  with_ocr_text=sum(1 for r in ok_records if r.ocr_text), described=sum(1 for r in ok_records if r.description),
                  **{f"status_{k}": v for k, v in counts.items()})
    log.info("Images: %s; %d image chunks", counts, len(chunks))
    return records


def image_file_path(settings: Settings, local_path: str) -> Path | None:
    """Resolve a stored relative path safely inside the images directory."""
    if not local_path:
        return None
    base = settings.images_dir.resolve()
    path = (base / local_path).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path
