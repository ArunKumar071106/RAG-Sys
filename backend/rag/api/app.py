"""FastAPI application.

Endpoints (all under /api):
  POST /chat                 grounded answer + sources + images
  POST /search/text          hybrid text retrieval (debug / integrations)
  POST /search/images        image retrieval
  GET  /sources/{chunk_id}   full text and metadata of one chunk
  GET  /images/{image_id}         image metadata
  GET  /images/{image_id}/file    the downloaded image file
  POST /feedback             👍 / 👎 on an answer (saved without personal details, emailed daily)
  GET  /health               liveness + component status
  GET  /status               crawl / extraction / indexing status
  POST /users                name + mobile number -> the token /chat needs (LOGIN_REQUIRED)
  GET  /answers/{id}         an answer the admin wrote (the source page of its citations)
  POST /admin/reindex        start a reindex job      (Bearer ADMIN_TOKEN)
  GET  /admin/jobs/{job_id}  reindex job status       (Bearer ADMIN_TOKEN)
  GET  /admin/dashboard      frequent questions, timings, unanswered questions, ratings (Bearer ADMIN_TOKEN)
  GET/POST/PUT/DELETE /admin/answers[/{id}]  the admin's answers; saving indexes them  (Bearer ADMIN_TOKEN)
  GET  /admin/users.xlsx     the visitors' names and phone numbers (Bearer ADMIN_TOKEN)
  GET/POST/DELETE /admin/files[/{id}]  uploaded PDF / Word / text files; indexed like pages (Bearer ADMIN_TOKEN)
  GET  /files/{id}           an uploaded file (the source page of its citations)
  POST /admin/reset-dashboard  the dashboard starts from zero (the logs are archived) (Bearer ADMIN_TOKEN)

Everything else is the chat page from frontend/ (plain HTML, CSS and JavaScript), so
http://127.0.0.1:8000/ is the whole assistant.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from rag import __version__
from rag.api.security import BodySizeLimitMiddleware, RateLimiter, make_admin_dependency, make_rate_limit_dependency
from rag.api.services import Services
from rag.config import Settings, get_settings
from rag.admin_answers import SOURCE_TITLE, AnswerStore
from rag.admin_files import MAX_BYTES, TYPES, BadFile, FileStore
from rag.dashboard import build_dashboard
from rag.feedback import FeedbackLog, daily_reports, email_configured
from rag.users import InvalidUser, UserStore
from rag.refresh import scheduled_refreshes
from rag.images.stage import image_file_path
from rag.index.indexer import manifest_path
from rag.llm.answer import ChatResult, ChatTurn
from rag.llm.client import LLMUnavailable
from rag.models import RetrievedChunk, RetrievedImage
from rag.utils import read_json

log = logging.getLogger("rag.api")


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    target: Literal["English"] = "English"


class TranslateResponse(BaseModel):
    text: str


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


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(default="", max_length=20_000)
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=1000)


class UserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=20)


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=8000)
    resolves: list[str] = Field(default_factory=list, max_length=50)  # the unanswered questions it answers


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=20)


class ReindexRequest(BaseModel):
    full: bool = False
    recrawl: bool = True


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Qdrant Cloud request is noise

    feedback = FeedbackLog(settings.data_dir / "feedback") if settings.feedback_enabled else None
    users = UserStore(settings.data_dir / "admin")
    admin_answers = AnswerStore(settings.data_dir / "admin")
    admin_files = FileStore(settings.data_dir / "admin")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = getattr(app.state, "services", None) is None
        if owned:
            app.state.services = Services(settings, background=True)
        # the daily email of unanswered questions and ratings, when an address and SMTP account are set
        reporter = asyncio.create_task(daily_reports(settings, feedback)) if feedback and email_configured(settings) else None
        # the monthly (REFRESH_EVERY_DAYS) crawl + index of the website, with an email of what changed
        refresher = asyncio.create_task(scheduled_refreshes(settings, app.state.services)) if settings.refresh_every_days else None
        yield
        for task in (reporter, refresher):
            if task:
                task.cancel()
        if owned:  # injected services belong to the caller
            app.state.services.close()

    app = FastAPI(title="Arivazhai - AAACET admission assistant API", version=__version__, lifespan=lifespan)
    app.state.services = services
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes,
                       larger={"/api/admin/files": MAX_BYTES + 1024})  # the admin's file uploads
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Arivazhai-User"],
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

    def visitor(x_arivazhai_user: str = Header(default="")) -> str | None:
        """The signed-in visitor (name + mobile number given); required for chatting when LOGIN_REQUIRED."""
        user_id = users.verify(x_arivazhai_user)
        if user_id is None and settings.login_required:
            raise HTTPException(status_code=401, detail="Please sign in with your name and mobile number to chat.")
        return user_id

    def check_length(text: str) -> None:
        if len(text) > settings.max_question_chars:
            raise HTTPException(status_code=422, detail=f"Message too long (max {settings.max_question_chars} characters)")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    # ------------------------------------------------------------------ chat
    @app.post("/api/chat", response_model=ChatResult, dependencies=[rate_limited])
    async def chat(body: ChatRequest, services: Services = Depends(ready), user_id: str | None = Depends(visitor)) -> ChatResult:
        check_length(body.message)
        if not services.corpus.chunks:
            raise HTTPException(status_code=503, detail="The knowledge base is empty. Run the crawl/index pipeline first.")
        started = time.monotonic()
        result = await services.answers.answer(body.message, body.history)
        if feedback:
            feedback.asked(body.message, result.mode, time.monotonic() - started)
        if user_id:
            await asyncio.to_thread(users.asked, user_id)
        if feedback and result.mode == "no_answer":
            # what people ask that the website does not answer: for the admission office's daily report
            feedback.unanswered(body.message, services.answers.retrieval_query(body.message, body.history))
        if services.suggester is not None:
            asked = [t.content for t in body.history if t.role == "user"]
            # "what about its labs?" after a CSE question is a CSE question: offer CSE follow-ups
            topic = services.answers.retrieval_query(body.message, body.history)
            result.follow_ups = services.suggester.follow_ups(topic, [*asked, body.message])
        return result

    @app.post("/api/translate", response_model=TranslateResponse, dependencies=[rate_limited])
    async def translate(body: TranslateRequest, services: Services = Depends(ready)) -> TranslateResponse:
        """English version of an answer given in another language (needs the AI answer service)."""
        try:
            return TranslateResponse(text=await services.answers.translate(body.text, body.target))
        except LLMUnavailable as exc:
            raise HTTPException(status_code=503, detail="Translation needs the AI answer service (GEMINI_API_KEY).") from exc

    @app.post("/api/feedback", dependencies=[rate_limited])
    def give_feedback(body: FeedbackRequest):
        """👍 / 👎 on an answer, with an optional comment; saved without personal details."""
        if feedback is None:
            raise HTTPException(status_code=404, detail="Feedback is turned off")
        feedback.rating(body.question, body.answer, body.rating, body.comment)
        return {"ok": True}

    @app.post("/api/users", dependencies=[rate_limited])
    def sign_in(body: UserRequest):
        """Name and mobile number before chatting; saved in DATA_DIR/admin/users.xlsx (admin only)."""
        try:
            user = users.register(body.name, body.phone)
        except InvalidUser as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"token": user["token"], "name": user["name"]}

    @app.get("/api/answers/{answer_id}", response_class=HTMLResponse)
    def admin_answer_page(answer_id: str):
        """The source page of an answer the admission office wrote (cited like a website page)."""
        entry = admin_answers.get(answer_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Answer not found")
        paragraphs = "".join(f"<p>{html.escape(p.strip())}</p>" for p in entry["answer"].split("\n\n") if p.strip())
        return HTMLResponse(
            f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            f"content=\"width=device-width, initial-scale=1\"><title>{SOURCE_TITLE}</title><style>body{{font-family:"
            f"system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#2d2d2d}}"
            f"h1{{font-size:1.3rem;color:#323496}}small{{color:#5b6472}}p{{white-space:pre-line}}</style></head><body>"
            f"<small>{SOURCE_TITLE} · AAA College of Engineering and Technology</small>"
            f"<h1>{html.escape(entry['question'])}</h1>{paragraphs}"
            f"<small>Updated {html.escape(entry.get('updated_at', '')[:10])}</small></body></html>",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

    # Type-ahead: cheap and called as people type, so it has its own, more generous limit.
    suggest_limited = Depends(make_rate_limit_dependency(RateLimiter(max(120, settings.rate_limit_per_minute * 6))))

    @app.get("/api/suggest", dependencies=[suggest_limited])
    def suggest(request: Request, q: str = "", limit: int = 6):
        services = svc(request)
        if services.suggester is None or len(q) > 200:
            return {"suggestions": []}
        return {"suggestions": services.suggester.suggest(q, max(1, min(limit, 10)))}

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

    @app.get("/api/admin/check", dependencies=[rate_limited, admin_only])
    def admin_check():
        """The admin panel's sign-in: is this the admin password (ADMIN_TOKEN)?"""
        return {"ok": True}

    @app.get("/api/admin/dashboard", dependencies=[admin_only])
    def dashboard(days: int = 30):
        return build_dashboard(settings, feedback, users.count(), max(1, min(days, 365)))

    @app.get("/api/admin/answers", dependencies=[admin_only])
    def list_answers():
        return sorted(admin_answers.all(), key=lambda e: e.get("updated_at", ""), reverse=True)

    def saved(entry: dict | None, request: Request) -> dict:
        job = svc(request).update_answers()  # chunk + embed + index, in the background
        return {"answer": entry, "indexing": job.id if job else "queued"}

    @app.post("/api/admin/answers", dependencies=[admin_only], status_code=201)
    def add_answer(body: AnswerRequest, request: Request):
        return saved(admin_answers.save(body.question, body.answer, resolves=body.resolves), request)

    @app.put("/api/admin/answers/{answer_id}", dependencies=[admin_only])
    def edit_answer(answer_id: str, body: AnswerRequest, request: Request):
        try:
            return saved(admin_answers.save(body.question, body.answer, answer_id, body.resolves), request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Answer not found") from exc

    @app.delete("/api/admin/answers/{answer_id}", dependencies=[admin_only])
    def delete_answer(answer_id: str, request: Request):
        if not admin_answers.delete(answer_id):
            raise HTTPException(status_code=404, detail="Answer not found")
        return saved(None, request)

    @app.post("/api/admin/reset-dashboard", dependencies=[admin_only])
    def reset_dashboard():
        """Start the dashboard from zero: questions, unanswered questions and ratings move to an archive folder."""
        if feedback is None:
            raise HTTPException(status_code=404, detail="Feedback is turned off")
        return {"archived": feedback.reset()}

    @app.get("/api/admin/files", dependencies=[admin_only])
    def list_files():
        return sorted(admin_files.all(), key=lambda e: e.get("uploaded_at", ""), reverse=True)

    @app.post("/api/admin/files", dependencies=[admin_only], status_code=201)
    async def upload_file(request: Request, name: str):
        """The file's bytes as the body, its name in ?name=; read, checked, kept, then indexed in the background."""
        data = bytearray()
        async for piece in request.stream():
            data.extend(piece)
            if len(data) > MAX_BYTES:
                raise HTTPException(status_code=413, detail=f"The file is too large (the limit is {MAX_BYTES // (1024 * 1024)} MB).")
        try:
            entry = await asyncio.to_thread(admin_files.add, name, bytes(data))
        except BadFile as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        job = svc(request).update_answers()
        return {"file": entry, "indexing": job.id if job else "queued"}

    @app.delete("/api/admin/files/{file_id}", dependencies=[admin_only])
    def delete_file(file_id: str, request: Request):
        if not admin_files.delete(file_id):
            raise HTTPException(status_code=404, detail="File not found")
        job = svc(request).update_answers()
        return {"indexing": job.id if job else "queued"}

    @app.get("/api/files/{file_id}")
    def uploaded_file(file_id: str):
        """An uploaded file, opened in the browser: the source of answers that cite it."""
        entry = admin_files.get(file_id)
        path = admin_files.path_of(entry) if entry else None
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        suffix = path.suffix.lower()
        return FileResponse(path, media_type=TYPES.get(suffix, "application/octet-stream"), filename=entry["name"],
                            content_disposition_type="inline" if suffix != ".docx" else "attachment",
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})

    @app.get("/api/admin/users.xlsx", dependencies=[admin_only])
    def users_file():
        if not users.path.exists():
            raise HTTPException(status_code=404, detail="Nobody has signed in yet")
        return FileResponse(users.path, filename="arivazhai-users.xlsx", headers={"Cache-Control": "no-store"},
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ------------------------------------------------------------------ the chat page
    page = settings.frontend_dir
    if page and (page / "index.html").is_file():
        @app.middleware("http")
        async def page_headers(request: Request, call_next):
            response = await call_next(request)
            if not request.url.path.startswith("/api/"):
                response.headers.setdefault("X-Content-Type-Options", "nosniff")
                response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                # the chat may be embedded on the official website (?embed=1), nowhere else
                response.headers.setdefault("Content-Security-Policy", f"frame-ancestors {FRAME_ANCESTORS}")
                if request.url.path in ("/", "/index.html", "/admin.html") or request.url.path.startswith(("/js/", "/css/")):
                    response.headers.setdefault("Cache-Control", "no-cache")  # a new version shows on the next visit
            return response

        app.mount("/", StaticFiles(directory=page, html=True), name="page")
    return app


FRAME_ANCESTORS = "'self' https://aaaenggcoll.ac.in https://www.aaaenggcoll.ac.in"

app = create_app()
