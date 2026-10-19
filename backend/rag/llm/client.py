"""LLM clients: Anthropic Claude (hosted) and an extractive no-LLM fallback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from rag.index.bm25 import tokenize
from rag.llm.prompts import SYSTEM_PROMPT
from rag.models import RetrievedChunk

log = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback ("fallbacks": "default").
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")


class LLMUnavailable(RuntimeError):
    """The hosted LLM could not produce an answer (credentials, network, rate limit...)."""


@dataclass
class LLMAnswer:
    text: str
    model: str
    refused: bool = False


class LLMClient(Protocol):
    name: str

    async def generate(self, system: str, messages: list[dict]) -> LLMAnswer: ...


class AnthropicLLM:
    def __init__(self, model: str, effort: str = "low", max_tokens: int = 16000, timeout: float = 90.0,
                 server_fallbacks: bool = True, client=None):
        import anthropic

        self.client = client or anthropic.AsyncAnthropic(timeout=timeout, max_retries=2)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.server_fallbacks = server_fallbacks and model.startswith(_FALLBACK_MODELS)
        self.name = f"anthropic:{model}"

    async def generate(self, system: str, messages: list[dict]) -> LLMAnswer:
        import anthropic

        params = dict(model=self.model, max_tokens=self.max_tokens, system=system, messages=messages,
                      output_config={"effort": self.effort})
        try:
            if self.server_fallbacks:
                response = await self.client.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                response = await self.client.messages.create(**params)
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailable("LLM authentication failed - check ANTHROPIC_API_KEY") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMUnavailable("LLM API key lacks permission for this model") from exc
        except anthropic.NotFoundError as exc:
            raise LLMUnavailable(f"LLM model {self.model!r} not found") from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailable("LLM rate limit reached") from exc
        except anthropic.BadRequestError as exc:
            raise LLMUnavailable(f"LLM rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"LLM API error (HTTP {exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable("Could not reach the LLM API") from exc

        if response.stop_reason == "refusal":
            return LLMAnswer(text="", model=response.model, refused=True)
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if response.stop_reason == "max_tokens":
            log.warning("LLM answer truncated at max_tokens=%s", self.max_tokens)
        return LLMAnswer(text=text, model=response.model)


class ExtractiveAnswerer:
    """No-LLM mode: quote the most query-relevant sentences from the top sources.

    Used when no API key is configured or the hosted LLM is unavailable. It can
    only repeat retrieved text, so it never invents facts.
    """

    name = "extractive"

    @staticmethod
    def _sentences(text: str) -> list[str]:
        from rag.chunking.text_chunker import split_sentences

        out: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # headings are context, not answers
            line = re.sub(r"^[-*•]\s+", "", line)
            if " | " in line:  # table rows stay whole
                out.append(line)
            else:
                out.extend(split_sentences(line))
        return out

    def __init__(self, term_weight=None):
        # term_weight(token) -> importance (e.g. BM25 IDF); rare terms decide which sentence is quoted
        self.term_weight = term_weight or (lambda token: 1.0)

    def answer(self, question: str, chunks: list[RetrievedChunk], max_sources: int = 3, per_source: int = 3,
               max_lines: int = 6, max_table_rows: int = 40, relevance: float = 0.5) -> str:
        """Markdown that quotes the website: one table, or short bullet lists grouped by page.

        Only sentences scoring at least ``relevance`` x the best one are quoted, so a question
        gets the lines that answer it rather than everything that shares a word with it.
        """
        from rag.retrieval.hybrid import chunk_title_text

        q = set(tokenize(question))
        # A sentence or table row is scored on its own words plus its page title and headings:
        # a row of the "Faculty List" table answers "IT faculty" though no cell says "faculty".
        scored: list[tuple[float, int, int, str, str]] = []  # (-score, source, position, key, sentence)
        for i, chunk in enumerate(chunks[:max_sources], start=1):
            title_terms = set(tokenize(chunk_title_text(chunk)))
            local: set[str] = set()
            for position, sentence in enumerate(self._sentences(chunk.text)):
                key = re.sub(r"\W+", " ", sentence.lower()).strip()
                if len(sentence) < 15 or key in local:
                    continue
                local.add(key)
                own = q & set(tokenize(sentence))
                score = sum(self.term_weight(t) for t in q & (set(tokenize(sentence)) | title_terms))
                if score > 0 and (own or " | " in sentence):
                    scored.append((-score, i, position, key, sentence))
        if not scored:
            return ""
        scored.sort()
        best = scored[0]
        # Several parts of one table among the sources, on another page whose title carries a
        # word of the question the best match's page lacks ("Faculty List" vs "Vision &
        # Mission" or "Industrial Visit" for "EEE faculty"): the question is about that table.
        sections: dict[tuple, int] = {}
        for part in chunks:
            sections[(part.doc_id, tuple(part.heading_path))] = sections.get((part.doc_id, tuple(part.heading_path)), 0) + 1
        best_page = chunks[best[1] - 1]
        best_title = q & set(tokenize(best_page.page_title))

        def names_more(part: RetrievedChunk) -> bool:
            return part.url != best_page.url and bool((q & set(tokenize(part.page_title))) - best_title)

        rows = [c for c in scored if " | " in c[4] and names_more(chunks[c[1] - 1])
                and sections[(chunks[c[1] - 1].doc_id, tuple(chunks[c[1] - 1].heading_path))] >= 2]
        if rows:
            best = rows[0]
        floor = -best[0] * relevance
        if " | " in best[4]:
            # the table is the answer (with a second table from the same page that matches as
            # well, e.g. "B.E. courses" next to "B.Tech courses"), plus the best plain sentences
            anchor = chunks[best[1] - 1]
            lines = self._quote_table(chunks, anchor, q, max_table_rows)
            for c in scored:
                other = chunks[c[1] - 1]
                if " | " in c[4] and -c[0] >= -best[0] * 0.9 and other.url == anchor.url \
                        and other.heading_path != anchor.heading_path:
                    lines += [""] + self._quote_table(chunks, other, q, max_table_rows)
                    break
            notes = [c for c in scored if c[1] == best[1] and " | " not in c[4] and -c[0] >= floor]
            if notes[:per_source]:
                lines += [""] + [f"- {sentence}" for *_, sentence in notes[:per_source]]
            return "\n".join(lines)

        # Short bullet lists grouped by page; table rows are left to the table answer above.
        groups: dict[str, tuple[list[int], list[str]]] = {}
        seen: set[str] = set()
        count = 0
        for neg, i, _, key, sentence in scored:
            if -neg < floor or count >= max_lines:
                break
            label = source_label(chunks[i - 1])
            sources, lines = groups.setdefault(label, ([], []))
            if " | " in sentence or key in seen or len(lines) >= per_source:
                continue
            seen.add(key)
            lines.append(sentence)
            if i not in sources:
                sources.append(i)
            count += 1
        blocks = [
            "\n".join([f"**{label}** " + "".join(f"[S{i}]" for i in sources), *(f"- {s}" for s in lines)])
            for label, (sources, lines) in groups.items() if lines
        ]
        return "\n\n".join(blocks)

    def _quote_table(self, chunks: list[RetrievedChunk], anchor: RetrievedChunk, q: set[str], max_rows: int) -> list[str]:
        """The anchor's whole table, across the sources holding its parts, as a compact Markdown table."""
        section = (anchor.doc_id, anchor.heading_path)
        rows: list[str] = []
        cited: list[int] = []
        seen: set[str] = set()
        for j, part in enumerate(chunks, start=1):
            if (part.doc_id, part.heading_path) != section:
                continue
            part_rows = [x for x in self._sentences(part.text) if " | " in x]
            if any(": " in r for r in part_rows):  # labelled rows repeat the header: drop the bare header line
                part_rows = [r for r in part_rows if ": " in r]
            for row in part_rows:
                key = re.sub(r"\W+", " ", row.lower()).strip()
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
                    if j not in cited:
                        cited.append(j)
        citations = "".join(f"[S{j}]" for j in cited)
        entries = f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}"
        heading = f"**{source_label(anchor)}** · {entries} {citations}"
        table = markdown_table(rows[:max_rows], q)
        if table is None:  # rows without column labels: quote them as they are
            return [heading, "", *(f"- {row}" for row in rows[:max_rows])]
        lines = [heading, "", *table]
        if len(rows) > max_rows:
            lines += ["", f"Showing the first {max_rows} of {len(rows)} entries; the source page has the rest."]
        return lines


def source_label(chunk: RetrievedChunk) -> str:
    """ "Faculty List – Artificial Intelligence and Data Science": the page and its main section."""
    title = chunk.page_title.strip()
    section = chunk.heading_path[0].strip() if chunk.heading_path else ""
    if section and section.lower() not in title.lower() and title.lower() not in section.lower():
        return f"{title} – {section}"
    return title or section


_SERIAL_RE = re.compile(r"^(s|sl|sr|emp)\.?\s*n(o|r)?\.?$|^(s\.?\s*)?no\.?$", re.I)
_BLANK_VALUES = {"", "-", "–", "—", "na", "n/a", "nil.", "--"}


def markdown_table(rows: list[str], q: set[str], max_columns: int = 5) -> list[str] | None:
    """Rows of "Header: value | Header: value" as a Markdown table of the most useful columns:
    serial numbers and mostly empty columns are dropped, columns named in the question come
    first, then the remaining ones in page order (short, plain labels before long official ones)."""
    parsed: list[dict[str, str]] = []
    columns: list[str] = []
    for row in rows:
        cells: dict[str, str] = {}
        for cell in row.split(" | "):
            if ": " not in cell:
                return None
            header, value = (x.strip() for x in cell.split(": ", 1))
            cells[header] = value
            if header not in columns:
                columns.append(header)
        parsed.append(cells)
    if not parsed:
        return None

    def filled(column: str) -> float:
        return sum(1 for r in parsed if r.get(column, "").lower() not in _BLANK_VALUES) / len(parsed)

    useful = [c for c in columns if not _SERIAL_RE.match(c.strip()) and filled(c) >= 0.5]
    named = [c for c in useful if q & set(tokenize(c))]
    short = [c for c in useful if c not in named and len(c) <= 40]
    rest = [c for c in useful if c not in named and c not in short]
    chosen = set((named + short + rest)[:max_columns])
    keep = [c for c in columns if c in chosen]
    if not keep:
        return None

    def cell(value: str) -> str:
        return "" if value.lower() in _BLANK_VALUES else value.replace("|", "/")

    return [
        "| " + " | ".join(keep) + " |",
        "|" + "|".join("---" for _ in keep) + "|",
        *("| " + " | ".join(cell(r.get(c, "")) for c in keep) + " |" for r in parsed),
    ]


def anthropic_credentials_present() -> bool:
    """True when the Anthropic SDK can resolve credentials (env vars or an `ant auth login` profile)."""
    import os
    from pathlib import Path

    if any(os.environ.get(v) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE",
                                         "ANTHROPIC_FEDERATION_RULE_ID")):
        return True
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (config_home / "anthropic").is_dir()


def get_llm(settings) -> AnthropicLLM | None:
    if settings.llm_provider != "anthropic":
        return None
    if not anthropic_credentials_present():
        log.warning("LLM_PROVIDER=anthropic but no Anthropic credentials found; using extractive answers")
        return None
    try:
        return AnthropicLLM(settings.llm_model, settings.llm_effort, settings.llm_max_tokens,
                            settings.llm_timeout_seconds, settings.llm_server_fallbacks)
    except Exception as exc:
        log.warning("Hosted LLM disabled: %s", exc)
        return None


__all__ = ["AnthropicLLM", "ExtractiveAnswerer", "LLMAnswer", "LLMClient", "LLMUnavailable", "SYSTEM_PROMPT", "get_llm"]
