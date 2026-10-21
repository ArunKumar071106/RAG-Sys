"""Answer-quality evaluation: does the answer to each question contain the fact a student needs?

Retrieval metrics (Recall@K, MRR) only check that the right page is found; an answer can still quote
the wrong section of it. Each line of the question file is {"question": ..., "expect": [...]}: the
answer passes when it contains one of the expected strings (case-insensitive).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnswerCase:
    question: str
    expect: list[str]


@dataclass
class AnswerReport:
    results: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        passed = sum(r["passed"] for r in self.results)
        return {
            "questions": len(self.results),
            "passed": passed,
            "accuracy": round(passed / len(self.results), 3) if self.results else 0.0,
            "failed": [{"question": r["question"], "expect": r["expect"], "answer": r["answer"][:240]}
                       for r in self.results if not r["passed"]],
        }


def load_cases(path: Path) -> list[AnswerCase]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            row = json.loads(line)
            cases.append(AnswerCase(row["question"], list(row["expect"])))
    return cases


def passes(answer: str, expect: list[str]) -> bool:
    text = answer.lower()
    return any(e.lower() in text for e in expect)


async def _run(answers, cases: list[AnswerCase]) -> AnswerReport:
    report = AnswerReport()
    for case in cases:
        result = await answers.answer(case.question)
        report.results.append({"question": case.question, "expect": case.expect, "answer": result.answer,
                               "passed": passes(result.answer, case.expect)})
    return report


def evaluate_answers(answers, cases: list[AnswerCase]) -> AnswerReport:
    return asyncio.run(_run(answers, cases))
