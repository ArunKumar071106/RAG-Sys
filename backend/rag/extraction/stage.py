"""Extraction stage: raw pages (JSONL) -> cleaned documents (JSONL)."""

from __future__ import annotations

import logging

from rag.config import Settings
from rag.extraction.boilerplate import drop_duplicate_documents, remove_repeated_blocks
from rag.extraction.html_extractor import extract_html, extract_pdf_text, extract_site_chrome
from rag.models import PageDocument, RawPage
from rag.utils import normalize_url, read_jsonl, update_status, write_jsonl

log = logging.getLogger(__name__)


def run_extraction(settings: Settings) -> list[PageDocument]:
    settings.ensure_dirs()
    docs: list[PageDocument] = []
    errors = 0
    home_urls = {normalize_url(u) for u in settings.crawl_start_urls}
    chrome_done = False
    for page in read_jsonl(settings.pages_file, RawPage):
        if page.status >= 400:
            continue
        try:
            if page.content_type.startswith("application/pdf"):
                doc = extract_pdf_text(page.text, page.url, page.title, page.fetched_at)
            else:
                doc = extract_html(page.html, page.url, settings.crawl_allowed_domains, page.fetched_at)
                if not chrome_done and normalize_url(page.url) in home_urls:
                    chrome = extract_site_chrome(page.html, page.url, settings.crawl_allowed_domains, page.fetched_at)
                    if chrome:
                        docs.append(chrome)
                        chrome_done = True
            docs.append(doc)
        except Exception:  # one malformed page must not stop the stage
            errors += 1
            log.exception("Failed to extract %s", page.url)

    docs = remove_repeated_blocks(docs, settings.boilerplate_page_ratio)
    unique, duplicates = drop_duplicate_documents(docs)
    write_jsonl(settings.documents_file, unique)
    write_jsonl(
        settings.processed_dir / "duplicate_pages.jsonl",
        [{"url": url, "duplicates": dups} for url, dups in duplicates.items()],
    )
    update_status(
        settings.status_file,
        "extract",
        documents=len(unique),
        duplicates=sum(len(v) for v in duplicates.values()),
        errors=errors,
        images_referenced=sum(len(d.images) for d in unique),
    )
    log.info("Extracted %d documents (%d duplicates, %d errors)", len(unique), sum(len(v) for v in duplicates.values()), errors)
    return unique


def load_duplicates(settings: Settings) -> dict[str, list[str]]:
    import json

    path = settings.processed_dir / "duplicate_pages.jsonl"
    result: dict[str, list[str]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                result[row["url"]] = row["duplicates"]
    return result
