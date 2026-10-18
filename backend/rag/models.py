"""Shared data models passed between pipeline stages and the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RawPage(BaseModel):
    """A fetched page as written by the crawler."""

    url: str
    status: int
    content_type: str = "text/html"
    html: str = ""
    text: str = ""  # used for PDFs (already extracted)
    title: str = ""
    depth: int = 0
    fetched_at: str = ""


class Link(BaseModel):
    url: str
    text: str = ""
    internal: bool = True


class ImageRef(BaseModel):
    """An image reference found while extracting a page (before download)."""

    url: str
    alt: str = ""
    title: str = ""
    caption: str = ""
    filename: str = ""
    heading_path: list[str] = Field(default_factory=list)
    context_before: str = ""
    context_after: str = ""
    width_attr: int | None = None
    height_attr: int | None = None
    source_page: str = ""
    page_title: str = ""
    is_background: bool = False


class Block(BaseModel):
    """A structural unit of a page, in document order."""

    type: Literal["heading", "text", "table"]
    text: str
    level: int = 0  # heading level (1-6) for headings
    heading_path: list[str] = Field(default_factory=list)
    rows: list[str] = Field(default_factory=list)  # table rows, header row first
    table_header: str = ""


class PageDocument(BaseModel):
    doc_id: str
    url: str
    title: str
    blocks: list[Block] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    content_hash: str = ""
    content_type: str = "text/html"
    fetched_at: str = ""
    kind: str = "page"  # page | section | news | document (from the CMS page type)


class TextChunk(BaseModel):
    chunk_id: str
    doc_id: str
    url: str
    page_title: str
    heading_path: list[str] = Field(default_factory=list)
    text: str
    token_count: int
    chunk_index: int
    content_hash: str
    duplicate_urls: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def embedding_text(self) -> str:
        crumbs = " > ".join([self.page_title, *self.heading_path]).strip(" >")
        return f"{crumbs}\n{self.text}" if crumbs else self.text


ImageStatus = Literal[
    "ok",
    "skipped_small",
    "invalid",
    "too_large",
    "http_error",
    "unsupported_type",
    "duplicate",
    "boilerplate",
]


class ImageRecord(BaseModel):
    image_id: str
    url: str
    local_path: str = ""
    sha256: str = ""
    ahash: str = ""
    mime_type: str = ""
    width: int = 0
    height: int = 0
    file_size: int = 0
    alt: str = ""
    title: str = ""
    caption: str = ""
    filename: str = ""
    source_page: str = ""
    page_title: str = ""
    heading: str = ""
    heading_path: list[str] = Field(default_factory=list)
    context: str = ""
    also_on_pages: list[str] = Field(default_factory=list)
    ocr_text: str = ""
    ocr_confidence: float = 0.0
    description: str = ""  # AI-generated, never shown as extracted fact
    description_model: str = ""
    keywords: list[str] = Field(default_factory=list)
    status: ImageStatus = "ok"
    error: str = ""
    duplicate_of: str = ""


class ImageChunk(BaseModel):
    chunk_id: str  # equal to image_id; one chunk per image
    image_id: str
    url: str
    source_page: str
    page_title: str
    heading: str
    text: str
    content_hash: str
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------- retrieval


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    url: str
    page_title: str
    heading_path: list[str]
    text: str
    score: float
    semantic_rank: int | None = None
    semantic_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None


class RetrievedImage(BaseModel):
    image_id: str
    url: str
    source_page: str
    page_title: str
    heading: str
    alt: str
    caption: str
    ocr_text: str
    description: str
    description_model: str
    width: int
    height: int
    score: float
    semantic_score: float | None = None
    bm25_score: float | None = None
