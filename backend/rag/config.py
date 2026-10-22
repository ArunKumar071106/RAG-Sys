"""Central configuration loaded from environment variables / .env.

Every tunable value lives here so nothing (keys, URLs, sizes) is hardcoded
elsewhere. Secrets are only ever read from the environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- storage -------------------------------------------------------
    data_dir: Path = Field(default=PROJECT_DIR / "data")

    # ---- crawling ------------------------------------------------------
    crawl_start_urls: CsvList = ["https://aaaenggcoll.ac.in/"]
    crawl_allowed_domains: CsvList = ["aaaenggcoll.ac.in", "www.aaaenggcoll.ac.in"]
    crawl_max_pages: int = 3000
    crawl_use_sitemaps: bool = True  # seed from robots.txt / wp-sitemap.xml sitemaps
    crawl_max_depth: int = 4
    crawl_delay_seconds: float = 1.0
    crawl_concurrency: int = 2
    crawl_timeout_seconds: int = 30
    crawl_user_agent: str = "AAACET-RAG-Bot/1.0 (+educational chatbot indexer)"
    crawl_obey_robots: bool = True
    crawl_include_pdfs: bool = True
    crawl_max_pdf_bytes: int = 15 * 1024 * 1024

    # ---- chunking ------------------------------------------------------
    chunk_size_tokens: int = 650
    chunk_overlap_tokens: int = 100
    chunk_min_tokens: int = 40
    boilerplate_page_ratio: float = 0.5

    # ---- images --------------------------------------------------------
    image_max_bytes: int = 10 * 1024 * 1024
    image_min_dimension: int = 80
    image_download_timeout: int = 30
    image_max_count: int = 1500
    image_allowed_domains: CsvList = []  # extra image/CDN hosts besides the crawl domains
    image_download_workers: int = 3
    ocr_engine: Literal["rapidocr", "tesseract", "none"] = "rapidocr"
    ocr_min_confidence: float = 0.6
    vision_enabled: bool = False
    vision_model: str = "claude-opus-5-5"
    vision_max_images: int = 300

    # ---- embeddings ----------------------------------------------------
    embedding_provider: Literal["bge-m3", "fastembed", "hashing"] = "bge-m3"
    # bge-small has a third of bge-base's parameters, so it indexes ~3x faster on a laptop CPU;
    # its benchmark retrieval scores are slightly lower. Set FASTEMBED_MODEL=BAAI/bge-base-en-v1.5 to trade back.
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    fastembed_cache_dir: str = ""
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16
    hashing_dim: int = 1024

    # ---- vector store --------------------------------------------------
    qdrant_url: str = ""  # empty => embedded local mode at qdrant_path
    qdrant_api_key: str = ""
    qdrant_path: Path | None = None
    qdrant_timeout: int = 120  # seconds per request to a Qdrant server; slow uplinks need long uploads
    qdrant_upsert_batch: int = 16  # points per upload to a Qdrant server (each carries its text)
    qdrant_text_collection: str = "aaacet_text"
    qdrant_image_collection: str = "aaacet_images"

    # ---- retrieval -----------------------------------------------------
    retrieval_top_k: int = 6
    semantic_candidates: int = 30
    bm25_candidates: int = 30
    rrf_k: int = 60
    image_top_k: int = 4
    image_min_semantic_score: float = 0.35
    text_min_semantic_score: float = 0.25
    min_query_coverage: float = 0.34  # IDF-weighted share of query terms a lexical-only hit must contain
    kind_weights: dict[str, float] = {"page": 1.0, "section": 1.0, "document": 0.95, "news": 0.85}
    title_boost: float = 0.03  # small tie-breaker when the question's terms appear in the page title/headings
    # Short forms people type -> the names the website uses; appended to the question before
    # searching (patterns are case-insensitive; "(?-i:...)" keeps one case-sensitive, e.g. "IT" vs "it").
    query_expansions: dict[str, str] = {
        r"AI\s*(?:&|and|-)?\s*DS|AIDS": "Artificial Intelligence and Data Science",
        r"CSE\s*\(?\s*CS\s*\)?|CSE\s*-?\s*cyber": "Computer Science and Engineering Cyber Security",
        r"CSE": "Computer Science and Engineering",
        r"ECE": "Electronics and Communication Engineering",
        r"EEE": "Electrical and Electronics Engineering",
        r"MECH": "Mechanical Engineering",
        r"(?-i:IT)": "Information Technology",
        r"S\s*&\s*H": "Science and Humanities",
        r"HOD|H\.O\.D": "Head of the Department",
    }
    # Words the website uses for a question's intent, added to the search (pattern -> words).
    query_synonyms: dict[str, str] = {
        r"\b(where|located|location|situated|how to reach)\b": "address",
        r"\b(phone|mobile|call|contact number)\b": "phone",
        r"\bseats?\b": "intake",
    }
    # Department names as the website writes them; type-ahead suggests questions about each.
    departments: CsvList = [
        "Artificial Intelligence and Data Science", "Computer Science and Engineering",
        "Computer Science and Engineering (Cyber Security)", "Electronics and Communication Engineering",
        "Electrical and Electronics Engineering", "Mechanical Engineering", "Civil Engineering",
        "Information Technology", "Science and Humanities", "Electronics Engineering (VLSI Design and Technology)",
    ]
    section_expand_max: int = 10  # the best match's whole section (e.g. all rows of a faculty table), up to this many chunks
    label_rank_weight: float = 3.0  # RRF weight of "Label: value" facts whose label the question names
    title_rank_weight: float = 6.0  # RRF weight of the title/headings field ranking (0 disables it)
    rerank_enabled: bool = False
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # ---- LLM -----------------------------------------------------------
    llm_provider: Literal["anthropic", "extractive"] = "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    llm_max_tokens: int = 16000
    llm_timeout_seconds: float = 90.0
    llm_server_fallbacks: bool = True
    llm_history_turns: int = 6

    # ---- API -----------------------------------------------------------
    cors_origins: CsvList = ["http://localhost:5173", "http://127.0.0.1:5173"]
    admin_token: str = ""
    rate_limit_per_minute: int = 30
    max_question_chars: int = 1000
    max_request_bytes: int = 64 * 1024
    log_level: str = "INFO"
    auto_index_on_startup: bool = True  # build the index at API start when only processed chunks exist

    @field_validator(
        "crawl_start_urls", "crawl_allowed_domains", "image_allowed_domains", "cors_origins", "departments", mode="before"
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                import json

                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        # A relative DATA_DIR (e.g. "./data" from .env) is relative to the project root,
        # not to whichever folder the command happens to run in.
        return value if value.is_absolute() else (PROJECT_DIR / value).resolve()

    @field_validator("chunk_overlap_tokens")
    @classmethod
    def _overlap_smaller_than_chunk(cls, value: int, info) -> int:
        size = info.data.get("chunk_size_tokens", 650)
        if value >= size:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
        return value

    # ---- derived paths -------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def qdrant_local_path(self) -> Path:
        return self.qdrant_path or (self.data_dir / "qdrant")

    @property
    def pages_file(self) -> Path:
        return self.raw_dir / "pages.jsonl"

    @property
    def documents_file(self) -> Path:
        return self.processed_dir / "documents.jsonl"

    @property
    def chunks_file(self) -> Path:
        return self.processed_dir / "chunks.jsonl"

    @property
    def images_file(self) -> Path:
        return self.processed_dir / "images.jsonl"

    @property
    def image_chunks_file(self) -> Path:
        return self.processed_dir / "image_chunks.jsonl"

    @property
    def status_file(self) -> Path:
        return self.data_dir / "status.json"

    def ensure_dirs(self) -> None:
        for path in (self.raw_dir, self.processed_dir, self.images_dir, self.index_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
