"""Command-line entry point.

    python -m rag.cli crawl                 # crawl the official site -> data/raw/pages.jsonl
    python -m rag.cli extract               # pages -> documents
    python -m rag.cli images                # download, validate, OCR, describe images
    python -m rag.cli chunk                 # documents -> text chunks
    python -m rag.cli index [--full]        # embed + Qdrant + BM25 (incremental by default)
    python -m rag.cli all [--full] [--skip-crawl]
    python -m rag.cli status
    python -m rag.cli check-qdrant          # is Qdrant Cloud / a Qdrant server set up and filled?
    python -m rag.cli search "hostel facilities"
    python -m rag.cli ask "What is the admission process?"
    python -m rag.cli eval [--questions eval/questions.jsonl] [--k 5]
    python -m rag.cli eval-answers [--questions eval/answers_aaacet.jsonl]
    python -m rag.cli eval-facts [--verbose]  # which facts of each answer are lost, and where
    python -m rag.cli demo                  # build + index the fictional demo site (offline)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from rag.config import BACKEND_DIR, get_settings


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_stage(args, settings) -> int:
    from rag.pipeline import run_crawl_subprocess, run_pipeline

    if args.command == "crawl" and getattr(args, "urls", None):
        run_crawl_subprocess(settings, str(Path(args.urls).resolve()))
        return 0

    stages = {"all": ("crawl", "extract", "images", "chunk", "index")}.get(args.command, (args.command,))
    if args.command == "all" and args.skip_crawl:
        stages = tuple(s for s in stages if s != "crawl")
    _print(run_pipeline(settings, stages, full=getattr(args, "full", False)))
    return 0


def cmd_status(args, settings) -> int:
    from rag.index.indexer import manifest_path
    from rag.utils import read_json

    manifest = read_json(manifest_path(settings))
    _print({"stages": read_json(settings.status_file),
            "index": {k: manifest.get(k) for k in ("embedder", "dim", "indexed_at", "counts")}})
    return 0


def cmd_check_qdrant(args, settings) -> int:
    """Check each step of moving the vectors to a Qdrant server, and say what to do next."""
    from urllib.parse import urlparse

    from rag.config import PROJECT_DIR
    from rag.index.indexer import _count_lines
    from rag.index.qdrant_store import QdrantStore

    logging.getLogger("httpx").setLevel(logging.WARNING)

    def line(ok: bool, text: str) -> None:
        print(f"[{'OK' if ok else '!!'}] {text}")

    def next_step(text: str) -> int:
        print(f"\nNEXT: {text}")
        return 1

    env_files = [p for p in (PROJECT_DIR / ".env", BACKEND_DIR / ".env") if p.exists()]
    line(bool(env_files), ".env file: " + (", ".join(str(p) for p in env_files) or f"none (expected {PROJECT_DIR / '.env'})"))
    if not settings.qdrant_url:
        line(False, "QDRANT_URL is empty: vectors are stored locally in " + str(settings.qdrant_local_path))
        return next_step(f"put QDRANT_URL=<your cluster URL>:6333 and QDRANT_API_KEY=<key> in {PROJECT_DIR / '.env'}, "
                         "save it, and run this check again.")
    host = urlparse(settings.qdrant_url).hostname or settings.qdrant_url
    line(True, f"QDRANT_URL points to {host}")
    cloud = host.endswith("cloud.qdrant.io")
    if settings.qdrant_api_key:
        line(True, f"QDRANT_API_KEY is set ({len(settings.qdrant_api_key)} characters; never shown)")
    else:
        line(not cloud, "QDRANT_API_KEY is empty" + (": Qdrant Cloud needs one" if cloud else ""))
        if cloud:
            return next_step("create an API key for the cluster on cloud.qdrant.io and put QDRANT_API_KEY=<key> in .env.")
    port = urlparse(settings.qdrant_url).port
    if cloud and port not in (None, 6333):  # no port is fine: the client adds :6333
        line(False, f"the URL ends with :{port}; Qdrant Cloud uses :6333")
        return next_step("end QDRANT_URL in .env with :6333 (or no port at all).")

    store = QdrantStore.from_settings(settings)
    try:
        counts = {name: store.count(name) for name in (settings.qdrant_text_collection, settings.qdrant_image_collection)}
    except Exception as exc:
        message = str(exc)
        line(False, f"cannot use the cluster: {type(exc).__name__}: {message.splitlines()[0][:200] if message else ''}")
        if "401" in message or "403" in message or "Unauthorized" in message or "Forbidden" in message:
            return next_step("the API key is wrong for this cluster: copy it again (no spaces or quotes) into .env.")
        return next_step("check the URL in .env, your internet connection, and that the cluster is running on cloud.qdrant.io.")
    finally:
        store.close()
    line(True, "connected to the cluster")

    expected = {settings.qdrant_text_collection: _count_lines(settings.chunks_file),
                settings.qdrant_image_collection: _count_lines(settings.image_chunks_file)}
    done = True
    for name, want in expected.items():
        have = counts[name]
        line(have >= want > 0 or want == have == 0, f"{name}: {have} of {want} vectors uploaded")
        done = done and have >= want
    if not done:
        return next_step("stop the backend (Ctrl+C), then run: python -m rag.cli index   "
                         "(it continues where the last upload stopped).")
    print("\nDONE: the vectors are in Qdrant. Start the backend and ask \"Eligibility\" in the app.")
    return 0


def _services(settings):
    from rag.api.services import Services

    services = Services(settings)
    if not services.ready:
        print(f"Services not ready: {services.error}", file=sys.stderr)
        sys.exit(2)
    return services


def cmd_search(args, settings) -> int:
    services = _services(settings)
    text = services.retriever.search_text(args.query, args.k)
    images = services.retriever.search_images(args.query, settings.image_top_k, text.chunks)
    _print({"text": [c.model_dump(exclude={"text"}) | {"snippet": c.text[:160]} for c in text.chunks],
            "images": [i.model_dump() for i in images]})
    services.close()
    return 0


def cmd_ask(args, settings) -> int:
    services = _services(settings)
    result = asyncio.run(services.answers.answer(args.question))
    print(result.answer)
    print()
    for s in result.sources:
        print(f"[{s.id}] {s.title} - {s.url}")
    for i in result.images:
        print(f"[{i.id}] image: {i.original_url} (on {i.source_page})")
    if result.notice:
        print(f"\nNote: {result.notice}")
    services.close()
    return 0


def cmd_eval(args, settings) -> int:
    from rag.eval.retrieval_eval import evaluate, load_questions

    services = _services(settings)
    report = evaluate(services.retriever, load_questions(Path(args.questions)), k_values=(1, 3, args.k))
    _print(report.summary())
    services.close()
    return 0 if report.questions else 1


def cmd_eval_answers(args, settings) -> int:
    from rag.eval.answer_eval import evaluate_answers, load_cases

    settings.llm_provider = "extractive"  # measures what students get without an API key
    services = _services(settings)
    report = evaluate_answers(services.answers, load_cases(Path(args.questions)))
    _print(report.summary())
    services.close()
    return 0


def cmd_eval_facts(args, settings) -> int:
    from rag.eval.fact_eval import evaluate_facts, load_fact_cases

    settings.llm_provider = "extractive"
    services = _services(settings)
    report = evaluate_facts(services, load_fact_cases(Path(args.questions)))
    if args.verbose:
        for r in report.results:
            got = sum(f["stage"] == "answer" for f in r["facts"])
            lost = "; ".join(f"{f['fact']} ({f['stage']})" for f in r["facts"] if f["stage"] != "answer")
            print(f"[{got}/{len(r['facts'])}] {r['question']}" + (f"  - missing: {lost}" if lost else ""))
    _print(report.summary())
    services.close()
    return 0


def cmd_demo(args, settings) -> int:
    """Build the fictional demo site, serve it locally and run the whole pipeline on it."""
    from rag.demo.site import build_demo_site, serve_directory
    from rag.pipeline import run_pipeline

    root = build_demo_site(settings.data_dir / "demo_site")
    server, base = serve_directory(root, args.port)
    print(f"Serving fictional demo site at {base}")
    settings.crawl_start_urls = [base + "/"]
    settings.crawl_allowed_domains = ["127.0.0.1"]
    settings.crawl_delay_seconds = 0.0
    try:
        _print(run_pipeline(settings, full=True))
    finally:
        server.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag", description="AAACET multimodal RAG pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("crawl")
    p.add_argument("--urls", help="file with one URL per line: fetch only these pages and merge them into the crawl")
    for name in ("extract", "images", "chunk"):
        sub.add_parser(name)
    p = sub.add_parser("index")
    p.add_argument("--full", action="store_true", help="drop and rebuild collections")
    p = sub.add_parser("all")
    p.add_argument("--full", action="store_true")
    p.add_argument("--skip-crawl", action="store_true")
    sub.add_parser("status")
    sub.add_parser("check-qdrant")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--k", type=int, default=6)
    p = sub.add_parser("ask")
    p.add_argument("question")
    p = sub.add_parser("eval")
    p.add_argument("--questions", default=str(BACKEND_DIR / "eval" / "questions_aaacet.jsonl"))
    p.add_argument("--k", type=int, default=5)
    p = sub.add_parser("eval-answers")
    p.add_argument("--questions", default=str(BACKEND_DIR / "eval" / "answers_aaacet.jsonl"))
    p = sub.add_parser("eval-facts")
    p.add_argument("--questions", default=str(BACKEND_DIR / "eval" / "facts_aaacet.jsonl"))
    p.add_argument("--verbose", action="store_true", help="one line per question with the facts it misses")
    p = sub.add_parser("demo")
    p.add_argument("--port", type=int, default=0)

    args = parser.parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers = {"status": cmd_status, "search": cmd_search, "ask": cmd_ask, "eval": cmd_eval,
                "eval-answers": cmd_eval_answers, "eval-facts": cmd_eval_facts, "check-qdrant": cmd_check_qdrant, "demo": cmd_demo}
    return handlers.get(args.command, cmd_stage)(args, settings)


if __name__ == "__main__":
    sys.exit(main())
