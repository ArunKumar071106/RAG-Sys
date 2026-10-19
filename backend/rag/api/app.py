"""FastAPI application.

Endpoints (all under /api):
  POST /chat                 grounded answer + sources + images
  POST /search/text          hybrid text retrieval (debug / integrations)
  POST /search/images        image retrieval
  GET  /sources/{chunk_id}   full text and metadata of one chunk
  GET  /images/{image_id}         image metadata
  GET  /images/{image_id}/file    the downloaded image file
  GET  /health               liveness + component status
  GET  /status               crawl / extraction / indexing status
  POST /admin/reindex        start a reindex job      (Bearer ADMIN_TOKEN)
  GET  /admin/jobs/{job_id}  reindex job status       (Bearer ADMIN_TOKEN)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from rag import __version__
from rag.api.security import BodySizeLimitMiddleware, RateLimiter, make_admin_dependency, make_rate_limit_dependency
from rag.api.services import Services
from rag.config import Settings, get_settings
from rag.images.stage import image_file_path
from rag.index.indexer import manifest_path
from rag.llm.answer import ChatResult, ChatTurn
from rag.models import RetrievedChunk, RetrievedImage
from rag.utils import read_json

log = logging.getLogger("rag.api")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)

    @field_validator("message")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        return value


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=20)


class ReindexRequest(BaseModel):
    full: bool = False
    recrawl: bool = True


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = getattr(app.state, "services", None) is None
        if owned:
            app.state.services = Services(settings, background=True)
        yield
        if owned:  # injected services belong to the caller
            app.state.services.close()

    app = FastAPI(title="AAACET Virtual Assistant API", version=__version__, lifespan=lifespan)
    app.state.services = services
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    rate_limited = Depends(make_rate_limit_dependency(RateLimiter(settings.rate_limit_per_minute)))
    admin_only = Depends(make_admin_dependency(settings.admin_token))

    def svc(request: Request) -> Services:
        return request.app.state.services

    def ready(request: Request) -> Services:
        services = svc(request)
        if services.starting:
            raise HTTPException(status_code=503, headers={"Retry-After": "30"},
                                detail="The assistant is starting up (the first start builds the search index). Try again shortly.")
        if not services.ready:
            raise HTTPException(status_code=503, detail="The assistant is not ready: " + (services.error or "index not loaded"))
        return services

    def check_length(text: str) -> None:
        if len(text) > settings.max_question_chars:
            raise HTTPException(status_code=422, detail=f"Message too long (max {settings.max_question_chars} characters)")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    # ------------------------------------------------------------------ chat
    @app.post("/api/chat", response_model=ChatResult, dependencies=[rate_limited])
    async def chat(body: ChatRequest, services: Services = Depends(ready)) -> ChatResult:
        check_length(body.message)
        if not services.corpus.chunks:
            raise HTTPException(status_code=503, detail="The knowledge base is empty. Run the crawl/index pipeline first.")
        return await services.answers.answer(body.message, body.history)

    @app.post("/api/search/text", response_model=list[RetrievedChunk], dependencies=[rate_limited])
    def search_text(body: SearchRequest, services: Services = Depends(ready)):
        check_length(body.query)
        return services.retriever.search_text(body.query, body.top_k).chunks

    @app.post("/api/search/images", response_model=list[RetrievedImage], dependencies=[rate_limited])
    def search_images(body: SearchRequest, services: Services = Depends(ready)):
        check_length(body.query)
        text = services.retriever.search_text(body.query, settings.retrieval_top_k)
        return services.retriever.search_images(body.query, body.top_k, text.chunks)

    # ------------------------------------------------------------------ sources / images
    @app.get("/api/sources/{chunk_id}")
    def source(chunk_id: str, services: Services = Depends(ready)):
        chunk = services.corpus.chunks.get(chunk_id)
        if chunk is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return chunk.model_dump()

    @app.get("/api/images/{image_id}")
    def image_meta(image_id: str, services: Services = Depends(ready)):
        record = services.corpus.images.get(image_id)
        if record is None or record.status != "ok":
            raise HTTPException(status_code=404, detail="Image not found")
        data = record.model_dump(exclude={"local_path", "sha256", "ahash"})
        data["description_is_ai_generated"] = bool(record.description)
        return data

    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, services: Services = Depends(ready)):
        record = services.corpus.images.get(image_id)
        if record is None or record.status != "ok":
            raise HTTPException(status_code=404, detail="Image not found")
        path = image_file_path(settings, record.local_path)
        if path is None:
            raise HTTPException(status_code=404, detail="Image file missing")
        return FileResponse(path, media_type=record.mime_type or "application/octet-stream",
                            headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})

    # ------------------------------------------------------------------ health / status
    @app.get("/api/health")
    def health(request: Request):
        services = svc(request)
        if services.starting or services.indexing:  # the vector index is being built: leave the store alone
            return {"status": "starting" if services.starting else "indexing", "version": __version__,
                    "ready": services.ready, "indexed": False, "error": "", "components": {}, "counts": {},
                    "search": "keyword" if services.indexing else "", "progress": services.index_progress}
        components = {"embedder": getattr(services.embedder, "name", None), "llm": getattr(services.llm, "name", None) or "extractive"}
        try:
            components["qdrant"] = "ok" if services.store is not None else "unavailable"
            counts = {
                "text_points": services.store.count(settings.qdrant_text_collection) if services.store else 0,
                "image_points": services.store.count(settings.qdrant_image_collection) if services.store else 0,
            }
        except Exception as exc:
            components["qdrant"] = f"error: {exc}"
            counts = {}
        indexed = bool(services.corpus and services.corpus.chunks)
        state = "ok" if services.ready and indexed else "degraded"
        search = "hybrid" if services.retriever is not None and services.retriever.semantic_enabled else "keyword"
        return {"status": state, "version": __version__, "ready": services.ready, "indexed": indexed,
                "error": services.error or services.index_error, "components": components, "counts": counts, "search": search}

    @app.get("/api/status")
    def pipeline_status(request: Request):
        services = svc(request)
        manifest = read_json(manifest_path(settings))
        return {
            "stages": read_json(settings.status_file),
            "index": {k: manifest.get(k) for k in ("embedder", "dim", "indexed_at", "counts")},
            "reindex_running": services.job_running,
        }

    # ------------------------------------------------------------------ admin
    @app.post("/api/admin/reindex", dependencies=[admin_only], status_code=202)
    def reindex(body: ReindexRequest, request: Request):
        try:
            job = svc(request).start_reindex(full=body.full, recrawl=body.recrawl)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return job.__dict__

    @app.get("/api/admin/jobs/{job_id}", dependencies=[admin_only])
    def job_status(job_id: str, request: Request):
        job = svc(request).jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.__dict__

    return app


app = create_app()
