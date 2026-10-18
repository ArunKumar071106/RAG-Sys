"""Retrieval evaluation with Recall@K and Mean Reciprocal Rank (MRR).

A question file is JSONL with one object per line:

    {"question": "...", "expected_url_patterns": ["admission"], "expected_image_patterns": ["notice"]}

A retrieved chunk is relevant when its URL contains (case-insensitively)
any expected pattern; patterns may also be regular expressions prefixed
with ``re:``. Results are de-duplicated by URL before ranking, so Recall@K
counts distinct pages.

    Recall@K = mean over questions of |relevant pages in top K| / |expected patterns|
    Hit@K    = fraction of questions with at least one relevant page in top K
    MRR      = mean of 1 / rank of the first relevant page (0 if none in the list)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field


class EvalQuestion(BaseModel):
    question: str
    expected_url_patterns: list[str] = Field(default_factory=list)
    expected_image_patterns: list[str] = Field(default_factory=list)
    answerable: bool = True


def load_questions(path: Path) -> list[EvalQuestion]:
    questions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            questions.append(EvalQuestion.model_validate(json.loads(line)))
    return questions


def _matches(url: str, pattern: str) -> bool:
    if pattern.startswith("re:"):
        return re.search(pattern[3:], url, re.I) is not None
    return pattern.lower() in url.lower()


def recall_at_k(urls: list[str], patterns: list[str], k: int) -> float:
    if not patterns:
        return 0.0
    top = urls[:k]
    found = sum(1 for p in patterns if any(_matches(u, p) for u in top))
    return found / len(patterns)


def reciprocal_rank(urls: list[str], patterns: list[str]) -> float:
    for rank, url in enumerate(urls, start=1):
        if any(_matches(url, p) for p in patterns):
            return 1.0 / rank
    return 0.0


def unique_urls(urls: list[str]) -> list[str]:
    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    return seen


@dataclass
class EvalReport:
    k_values: tuple[int, ...]
    questions: int = 0
    recall: dict[int, float] = field(default_factory=dict)
    hit: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    image_hit: float | None = None
    unanswerable_rejected: float | None = None
    per_question: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "questions": self.questions,
            **{f"recall@{k}": round(v, 3) for k, v in self.recall.items()},
            **{f"hit@{k}": round(v, 3) for k, v in self.hit.items()},
            "mrr": round(self.mrr, 3),
            "image_hit": None if self.image_hit is None else round(self.image_hit, 3),
            "unanswerable_rejected": None if self.unanswerable_rejected is None else round(self.unanswerable_rejected, 3),
            "per_question": self.per_question,
        }


def evaluate(retriever, questions: list[EvalQuestion], k_values: tuple[int, ...] = (1, 3, 5)) -> EvalReport:
    k_values = tuple(sorted(set(k_values)))
    report = EvalReport(k_values=k_values)
    answerable = [q for q in questions if q.answerable and q.expected_url_patterns]
    unanswerable = [q for q in questions if not q.answerable]
    recall_sums = {k: 0.0 for k in k_values}
    hit_sums = {k: 0.0 for k in k_values}
    rr_sum = 0.0
    image_total = image_hits = 0
    depth = max(k_values)

    for q in answerable:
        result = retriever.search_text(q.question, max(depth * 2, 10))
        urls = unique_urls([c.url for c in result.chunks])
        rr = reciprocal_rank(urls, q.expected_url_patterns)
        rr_sum += rr
        row = {"question": q.question, "rr": round(rr, 3), "top_urls": urls[:depth]}
        for k in k_values:
            r = recall_at_k(urls, q.expected_url_patterns, k)
            recall_sums[k] += r
            hit_sums[k] += 1.0 if r > 0 else 0.0
        if q.expected_image_patterns:
            image_total += 1
            images = retriever.search_images(q.question, 4, result.chunks)
            hit = any(_matches(i.url, p) for i in images for p in q.expected_image_patterns)
            image_hits += hit
            row["image_hit"] = hit
        report.per_question.append(row)

    rejected = 0
    for q in unanswerable:
        result = retriever.search_text(q.question, depth)
        rejected += not result.chunks
        report.per_question.append({"question": q.question, "answerable": False, "rejected": not result.chunks})

    n = len(answerable)
    report.questions = n + len(unanswerable)
    if n:
        report.recall = {k: recall_sums[k] / n for k in k_values}
        report.hit = {k: hit_sums[k] / n for k in k_values}
        report.mrr = rr_sum / n
    if image_total:
        report.image_hit = image_hits / image_total
    if unanswerable:
        report.unanswerable_rejected = rejected / len(unanswerable)
    return report
