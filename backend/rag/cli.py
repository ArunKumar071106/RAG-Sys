"""Command-line entry point.

    python -m rag.cli crawl                 # crawl the official site -> data/raw/pages.jsonl
    python -m rag.cli extract               # pages -> documents
    python -m rag.cli images                # download, validate, OCR, describe images
    python -m rag.cli chunk                 # documents -> text chunks
    python -m rag.cli index [--full]        # embed + Qdrant + BM25 (incremental by default)
    python -m rag.cli all [--full] [--skip-crawl]
    python -m rag.cli status
    python -m rag.cli search "hostel facilities"
    python -m rag.cli ask "What is the admission process?"
    python -m rag.cli eval [--questions eval/questions.jsonl] [--k 5]
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
    from rag.pipeline import run_pipeline

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
    for name in ("crawl", "extract", "images", "chunk"):
        sub.add_parser(name)
    p = sub.add_parser("index")
    p.add_argument("--full", action="store_true", help="drop and rebuild collections")
    p = sub.add_parser("all")
    p.add_argument("--full", action="store_true")
    p.add_argument("--skip-crawl", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--k", type=int, default=6)
    p = sub.add_parser("ask")
    p.add_argument("question")
    p = sub.add_parser("eval")
    p.add_argument("--questions", default=str(BACKEND_DIR / "eval" / "questions_aaacet.jsonl"))
    p.add_argument("--k", type=int, default=5)
    p = sub.add_parser("demo")
    p.add_argument("--port", type=int, default=0)

    args = parser.parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers = {"status": cmd_status, "search": cmd_search, "ask": cmd_ask, "eval": cmd_eval, "demo": cmd_demo}
    return handlers.get(args.command, cmd_stage)(args, settings)


if __name__ == "__main__":
    sys.exit(main())
