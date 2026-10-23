"""Where an answer's facts are lost.

Each case lists the facts a complete answer must contain, copied from the live website. Every fact
is traced through the pipeline and ends at the last stage that still holds it:

    answer      in the answer shown to the student
    context     in the sections handed to the answer composer, but left out of the answer
    candidates  in the top 40 search results, but ranked below the ones the answer uses
    kb          in the knowledge base, but search does not find it
    image_only  only in the text read from an image
    not_in_kb   not in the knowledge base at all (a scanned PDF, a page the crawl never reached, ...)
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

STAGES = ("answer", "context", "candidates", "kb", "image_only", "not_in_kb")


@dataclass
class FactCase:
    question: str
    facts: list[str]
    split: str = ""


@dataclass
class FactReport:
    results: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        out: dict = {}
        for split in sorted({r["split"] for r in self.results}) or [""]:
            rows = [r for r in self.results if r["split"] == split]
            stages = Counter(f["stage"] for r in rows for f in r["facts"])
            total = sum(stages.values()) or 1
            out[split or "all"] = {
                "questions": len(rows),
                "facts_in_answer": round(sum(sum(f["stage"] == "answer" for f in r["facts"]) / len(r["facts"])
                                             for r in rows) / max(len(rows), 1), 3),
                "complete_answers": sum(all(f["stage"] == "answer" for f in r["facts"]) for r in rows),
                "stages": {s: round(stages[s] / total, 3) for s in STAGES if stages[s]},
            }
        return out


def load_fact_cases(path: Path) -> list[FactCase]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            row = json.loads(line)
            cases.append(FactCase(row["question"], list(row["facts"]), row.get("split", "")))
    return cases


def normalize(text: str) -> str:
    """Lower case, plain quotes and dashes, no Markdown marks: "**Dr. M. Sekar**" matches "Dr. M. Sekar"."""
    text = text.lower().translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                                 "–": "-", "—": "-", "\xa0": " "}))
    return re.sub(r"\s+", " ", re.sub(r"[*|#_`>\[\]]", " ", text)).strip()


def _chunk_text(chunk) -> str:
    return normalize(" ".join([chunk.page_title, *(chunk.heading_path or []), chunk.text]))


async def _run(services, cases: list[FactCase], depth: int = 40) -> FactReport:
    retriever, answers = services.retriever, services.answers
    kb = [_chunk_text(c) for c in retriever.corpus.chunks.values()]
    kb_images = [normalize(c.text) for c in retriever.corpus.image_chunks.values()]
    report = FactReport()
    for case in cases:
        query = await answers.search_query(case.question, [])
        candidates = [_chunk_text(c) for c in retriever.search_text(query, depth).chunks]
        top = retriever.search_text(query, answers.top_k).chunks
        context = [_chunk_text(c) for c in retriever.expand_section(retriever.with_parent_overview(list(top)))]
        result = await answers.answer(case.question)
        answer = normalize(result.answer)
        facts = []
        for fact in case.facts:
            f = normalize(fact)
            rank = next((i for i, text in enumerate(candidates, start=1) if f in text), None)
            stage = ("answer" if f in answer else "context" if any(f in t for t in context) else
                     "candidates" if rank else "kb" if any(f in t for t in kb) else
                     "image_only" if any(f in t for t in kb_images) else "not_in_kb")
            facts.append({"fact": fact, "stage": stage, "rank": rank})
        report.results.append({"question": case.question, "split": case.split, "facts": facts,
                               "answer": result.answer})
    return report


def evaluate_facts(services, cases: list[FactCase]) -> FactReport:
    return asyncio.run(_run(services, cases))
