"""Scrapy spider for the official AAACET website.

* Stays on the allowed domains.
* Obeys robots.txt (ROBOTSTXT_OBEY) and uses polite delays/AutoThrottle.
* Yields one item per HTML page or PDF; binary assets are skipped here
  (images are downloaded later by the image stage with their own limits).
"""

from __future__ import annotations

import io
import logging
import re

import scrapy
from scrapy.http import Response, TextResponse

from rag.utils import is_allowed_host, normalize_url, utc_now

log = logging.getLogger(__name__)

SKIP_EXT_RE = re.compile(
    r"\.(jpe?g|png|gif|webp|bmp|svg|ico|tiff?|avif|css|js|json|xml|zip|rar|7z|gz|tar|mp4|mp3|avi|mov|wmv|webm|"
    r"doc|docx|xls|xlsx|ppt|pptx|exe|apk|woff2?|ttf|eot)$",
    re.I,
)
SKIP_PATH_RE = re.compile(r"/(wp-admin|wp-login|wp-json|feed|xmlrpc|cgi-bin|login|logout|cart|checkout)(/|$)|[?&](replytocom|share)=", re.I)


class AaacetSpider(scrapy.Spider):
    name = "aaacet"

    def __init__(self, start_urls: list[str], allowed_domains: list[str], max_pages: int = 400,
                 include_pdfs: bool = True, max_pdf_bytes: int = 15 * 1024 * 1024, **kwargs):
        super().__init__(**kwargs)
        self.start_urls = start_urls
        self.allowed_domains = allowed_domains
        self.max_pages = max_pages
        self.include_pdfs = include_pdfs
        self.max_pdf_bytes = max_pdf_bytes
        self.pages_seen = 0

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, meta={"depth": 0})

    def _should_follow(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        if not is_allowed_host(url, self.allowed_domains):
            return False
        path = url.split("?", 1)[0]
        if SKIP_PATH_RE.search(url):
            return False
        if path.lower().endswith(".pdf"):
            return self.include_pdfs
        return not SKIP_EXT_RE.search(path)

    def parse(self, response: Response):
        if self.pages_seen >= self.max_pages:
            return
        content_type = response.headers.get("Content-Type", b"").decode("latin-1").lower()
        url = normalize_url(response.url)
        depth = response.meta.get("depth", 0)

        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            item = self._pdf_item(response, url, depth)
            if item:
                self.pages_seen += 1
                yield item
            return

        if not isinstance(response, TextResponse) or "html" not in content_type and content_type:
            return

        self.pages_seen += 1
        yield {
            "url": url,
            "status": response.status,
            "content_type": "text/html",
            "html": response.text,
            "title": (response.css("title::text").get() or "").strip(),
            "depth": depth,
            "fetched_at": utc_now(),
        }

        for href in response.css("a::attr(href)").getall():
            href = href.strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            next_url = normalize_url(href, response.url)
            if self._should_follow(next_url):
                yield response.follow(next_url, callback=self.parse, meta={"depth": depth + 1})

    def _pdf_item(self, response: Response, url: str, depth: int) -> dict | None:
        if not self.include_pdfs or len(response.body) > self.max_pdf_bytes:
            return None
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(response.body))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:60])
            title = ""
            if reader.metadata and reader.metadata.title:
                title = str(reader.metadata.title)
        except Exception as exc:  # corrupt / encrypted PDFs
            log.warning("Could not read PDF %s: %s", url, exc)
            return None
        if not text.strip():
            return None  # scanned PDFs without a text layer are skipped
        return {
            "url": url,
            "status": response.status,
            "content_type": "application/pdf",
            "html": "",
            "text": text,
            "title": title,
            "depth": depth,
            "fetched_at": utc_now(),
        }
