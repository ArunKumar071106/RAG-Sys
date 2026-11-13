"""The answer checks run the way students get answers: the real search model, Qdrant and the AI model.

`python -m rag.cli eval-live` asks every question of eval/answers_aaacet.jsonl (and the held-out set)
through the configured answer model (Gemini by default), and writes a report of what passed, what
failed and how each answer was made (AI, quoted from the website, not found) to data/reports/.
The other evals measure the search with a stand-in model and no AI; this one measures what your
setup really answers. It waits a few seconds between questions, under Gemini's free-tier rate limit.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rag.eval.answer_eval import AnswerCase, passes


@dataclass
class LiveReport:
    model: str
    results: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(r["passed"] for r in self.results)

    def markdown(self) -> str:
        n = len(self.results)
        modes = {m: sum(r["mode"] == m for r in self.results) for m in ("llm", "extractive", "no_answer")}
        seconds = sorted(r["seconds"] for r in self.results) or [0.0]
        lines = [
            f"# Arivazhai live answer check, {datetime.now():%d %b %Y %H:%M}",
            "",
            f"Answer model: {self.model or 'none (quotes the website)'}",
            "",
            f"**{self.passed} of {n} answers contain the expected fact** ({self.passed / n:.0%})." if n else "No questions.",
            "",
            f"Written by the AI: {modes['llm']} · quoted from the website (no AI, or the AI failed): {modes['extractive']}"
            f" · not found: {modes['no_answer']}",
            f"Time per answer: median {seconds[len(seconds) // 2]:.1f} s, slowest {seconds[-1]:.1f} s",
            "",
            "## Failed",
            "",
        ]
        failed = [r for r in self.results if not r["passed"]]
        for r in failed:
            lines += [f"### {r['question']}", f"Expected: {' / '.join(r['expect'])} · made by: {r['mode']} · {r['seconds']:.1f} s",
                      "", "> " + r["answer"][:700].replace("\n", "\n> "), ""]
        if not failed:
            lines += ["None.", ""]
        lines += ["## All questions", "", "| | Question | Made by | Time |", "|---|---|---|---|"]
        lines += [f"| {'✅' if r['passed'] else '❌'} | {r['question']} | {r['mode']} | {r['seconds']:.1f} s |" for r in self.results]
        return "\n".join(lines) + "\n"


async def run_live(answers, cases: list[AnswerCase], pause: float = 4.0, progress=print) -> LiveReport:
    report = LiveReport(model=getattr(answers.llm, "name", "") if answers.llm is not None else "")
    for i, case in enumerate(cases, start=1):
        start = time.perf_counter()
        result = await answers.answer(case.question)
        seconds = time.perf_counter() - start
        ok = passes(result.answer, case.expect)
        report.results.append({"question": case.question, "expect": case.expect, "answer": result.answer, "mode": result.mode,
                               "seconds": seconds, "passed": ok})
        progress(f"[{i}/{len(cases)}] {'OK  ' if ok else 'FAIL'} {result.mode:10} {seconds:5.1f} s  {case.question}")
        if pause and i < len(cases):
            await asyncio.sleep(pause)  # Gemini's free tier allows only a few requests a minute
    return report


def write_report(report: LiveReport, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"live-eval-{datetime.now():%Y%m%d-%H%M}.md"
    path.write_text(report.markdown(), encoding="utf-8")
    return path
