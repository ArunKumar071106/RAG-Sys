"""Run the crawler and write ``data/raw/pages.jsonl``.

Scrapy's Twisted reactor cannot be restarted inside one process, so the
crawl is meant to be launched as its own process (``python -m rag.cli crawl``
or the admin reindex job, which spawns a subprocess).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from scrapy.logformatter import LogFormatter

from rag.config import Settings, get_settings
from rag.utils import update_status, utc_now

log = logging.getLogger(__name__)


class JsonlWriterPipeline:
    """Scrapy item pipeline that de-duplicates by URL and appends JSONL."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.seen: set[str] = set()
        self.count = 0
        self.fh = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("RAG_PAGES_FILE"))

    def open_spider(self, spider=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = self.path.with_suffix(".jsonl.partial")
        self.fh = self.tmp.open("w", encoding="utf-8")

    def close_spider(self, spider=None):
        if self.fh:
            self.fh.close()
            self.tmp.replace(self.path)

    def process_item(self, item, spider=None):
        url = item["url"]
        if url in self.seen:
            return item
        self.seen.add(url)
        self.fh.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
        self.count += 1
        return item


class QuietLogFormatter(LogFormatter):
    """Never dump scraped items (whole HTML pages) into the log; per-page lines go to DEBUG."""

    def scraped(self, item, response, spider):
        return None

    def crawled(self, request, response, spider):
        entry = super().crawled(request, response, spider)
        entry["level"] = logging.DEBUG
        return entry


def scrapy_settings(settings: Settings) -> dict:
    return {
        "BOT_NAME": "aaacet_rag",
        "USER_AGENT": settings.crawl_user_agent,
        "ROBOTSTXT_OBEY": settings.crawl_obey_robots,
        "DOWNLOAD_DELAY": settings.crawl_delay_seconds,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": settings.crawl_concurrency * 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": settings.crawl_concurrency,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": settings.crawl_delay_seconds,
        "AUTOTHROTTLE_MAX_DELAY": 30,
        # DOWNLOAD_DELAY still caps the rate at ~1 request/second per domain
        "AUTOTHROTTLE_TARGET_CONCURRENCY": float(settings.crawl_concurrency),
        "DOWNLOAD_TIMEOUT": settings.crawl_timeout_seconds,
        "DOWNLOAD_MAXSIZE": max(settings.crawl_max_pdf_bytes, 20 * 1024 * 1024),
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "DEPTH_LIMIT": settings.crawl_max_depth,
        "CLOSESPIDER_ITEMCOUNT": settings.crawl_max_pages,
        "COOKIES_ENABLED": False,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
        "LOG_FORMATTER": "rag.crawler.run.QuietLogFormatter",
        "ITEM_PIPELINES": {"rag.crawler.run.JsonlWriterPipeline": 100},
        "RAG_PAGES_FILE": str(settings.pages_file),
        "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    }


def run_crawl(settings: Settings | None = None) -> int:
    from scrapy.crawler import CrawlerProcess

    from rag.crawler.spider import AaacetSpider

    settings = settings or get_settings()
    settings.ensure_dirs()
    update_status(settings.status_file, "crawl", state="running", started_at=utc_now())
    process = CrawlerProcess(scrapy_settings(settings))
    crawler = process.create_crawler(AaacetSpider)
    process.crawl(
        crawler,
        start_urls=settings.crawl_start_urls,
        allowed_domains=settings.crawl_allowed_domains,
        max_pages=settings.crawl_max_pages,
        include_pdfs=settings.crawl_include_pdfs,
        max_pdf_bytes=settings.crawl_max_pdf_bytes,
        use_sitemaps=settings.crawl_use_sitemaps,
    )
    process.start()
    stats = crawler.stats.get_stats() if crawler.stats else {}
    pages = sum(1 for _ in settings.pages_file.open(encoding="utf-8")) if settings.pages_file.exists() else 0
    update_status(
        settings.status_file,
        "crawl",
        state="finished",
        finished_at=utc_now(),
        pages=pages,
        robots_forbidden=stats.get("robotstxt/forbidden", 0),
        http_errors=stats.get("spider_exceptions/count", 0) + stats.get("downloader/exception_count", 0),
    )
    log.info("Crawl finished: %d pages", pages)
    return pages


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("scrapy").setLevel(logging.INFO)
    sys.exit(0 if run_crawl() > 0 else 1)
