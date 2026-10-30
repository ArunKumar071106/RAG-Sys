"""LLM clients: Anthropic Claude (hosted) and an extractive no-LLM fallback."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

from rag.chunking.tokens import count_tokens
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

    def __init__(self, term_weight=None, whole_sections: bool = True):
        # term_weight(token) -> importance (e.g. BM25 IDF); rare terms decide which sentence is quoted
        self.term_weight = term_weight or (lambda token: 1.0)
        # quote the best sections in search order (lists, sub-headings and tables kept) instead of
        # picking single sentences that share words with the question
        self.whole_sections = whole_sections

    def answer(self, question: str, chunks: list[RetrievedChunk], max_sources: int = 3, per_source: int = 3,
               max_lines: int = 6, max_table_rows: int = 40, relevance: float = 0.5) -> str:
        """Markdown that quotes the website: one table, or short bullet lists grouped by page.

        Only sentences scoring at least ``relevance`` x the best one are quoted, so a question
        gets the lines that answer it rather than everything that shares a word with it.
        """
        from rag.retrieval.hybrid import chunk_title_text

        q = set(tokenize(question))
        if self.whole_sections:
            return self._quote_sections(q, chunks, max_sections=max_sources, max_table_rows=max_table_rows)
        section = self._section_answer(q, chunks[:max_sources])
        if section:
            return section
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
            # The table is the answer. Tables that match about as well are shown too: first the
            # one whose page title names more of the question ("Faculty List" before "Governance"
            # for "AI&DS faculty"), then the bigger ("EEE faculty" lists the department's faculty
            # before its two visiting professors; intake shows both B.E. and B.Tech tables).
            def key_of(part: RetrievedChunk) -> tuple:
                return part.doc_id, tuple(part.heading_path)

            def size(part: RetrievedChunk) -> int:
                return sum(len([x for x in self._sentences(c.text) if " | " in x]) for c in chunks if key_of(c) == key_of(part))

            tables: list[RetrievedChunk] = []
            for c in scored:
                part = chunks[c[1] - 1]
                if " | " in c[4] and -c[0] >= -best[0] * 0.9 and key_of(part) not in {key_of(t) for t in tables}:
                    tables.append(part)
            named = {key_of(t): len(q & set(tokenize(t.page_title))) for t in tables}
            tables = sorted(tables[:2], key=lambda t: (-named[key_of(t)], -size(t)))
            tables = [t for t in tables if named[key_of(t)] == named[key_of(tables[0])]]  # not "Governance" after "Faculty List"
            lines: list[str] = []
            for table in tables:
                lines += ([""] if lines else []) + self._quote_table(chunks, table, q, max_table_rows)
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
            label = source_label(chunks[i - 1], q)
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

    def _section_answer(self, q: set[str], chunks: list[RetrievedChunk], coverage: float = 0.7,
                        max_tokens: int = 320, max_lines: int = 12) -> str:
        """A short prose section whose title names the question ("TNEA B.E./B.Tech. Eligibility",
        "Fees", "Required Documents") is quoted whole, its sub-headings kept as labels: picking
        sentences by shared words would drop the line that answers it ("... 45% ...")."""
        if not q:
            return ""
        total = sum(self.term_weight(t) for t in q)
        shares: list[float] = []
        for chunk in chunks:
            headings = [*chunk.heading_path, *re.findall(r"^#{1,6}\s+(.+)$", chunk.text, re.M)]
            named = q & set(tokenize(" ".join([*headings, chunk.page_title.split(" – ")[0]])))
            # the section must be named by the question, not just sit on a page that is
            shares.append(sum(self.term_weight(t) for t in named) / total if q & set(tokenize(" ".join(headings))) else 0.0)
        top = max(shares, default=0.0)
        if top < coverage:
            return ""
        # the best-named result, in search order: when that is a table or a long page, the table
        # and sentence answers handle it
        first = next(i for i, share in enumerate(shares) if share >= top - 0.05)
        if count_tokens(chunks[first].text) > max_tokens or " | " in chunks[first].text:
            return ""
        # equally named sections of the same page are all quoted ("Eligibility": B.E., M.E., Ph.D.)
        picked = [i for i, share in enumerate(shares) if share >= shares[first] - 0.05 and chunks[i].url == chunks[first].url
                  and " | " not in chunks[i].text and count_tokens(chunks[i].text) <= max_tokens][:3]
        blocks = []
        for i in picked:
            lines = self._section_lines(chunks[i], max_lines if len(picked) == 1 else max_lines // 2)
            if lines:
                blocks.append("\n".join([f"**{source_label(chunks[i], q)}** [S{i + 1}]", *lines]))
        return "\n\n".join(blocks)

    @staticmethod
    def _section_lines(chunk: RetrievedChunk, max_lines: int) -> list[str]:
        lines: list[str] = []
        label = ""
        for raw in chunk.text.splitlines():
            line = raw.strip()
            heading = re.match(r"^#{1,6}\s+(.+)$", line)
            if heading:
                label = heading.group(1).strip() if heading.group(1).strip() not in chunk.heading_path else ""
                continue
            line = re.sub(r"^[-*•]\s+", "", line)
            if len(line) < 3:
                continue
            lines.append(f"- **{label}:** {line}" if label else f"- {line}")
            label = ""
            if len(lines) >= max_lines:
                break
        return lines

    def _quote_sections(self, q: set[str], chunks: list[RetrievedChunk], max_sections: int = 3,
                        budgets: tuple[int, ...] = (24, 10, 8), max_table_rows: int = 40) -> str:
        """The best search results' sections quoted in search order: the first one at length, the
        next ones shorter, and only while they still share most of the question's weight with
        it. Each chunk is one topic, so its lines answer together ("documents required": every
        certificate, not the one line that says "documents")."""
        from rag.retrieval.hybrid import chunk_title_text

        groups: dict[tuple, list[tuple[int, RetrievedChunk]]] = {}
        for i, chunk in enumerate(chunks, start=1):
            groups.setdefault((chunk.url, tuple(chunk.heading_path)), []).append((i, chunk))
        total = sum(self.term_weight(t) for t in q) or 1.0

        def share(parts: list[tuple[int, RetrievedChunk]]) -> float:
            words = set(tokenize(chunk_title_text(parts[0][1])))
            for _, part in parts:
                words |= set(tokenize(part.text))
            return sum(self.term_weight(t) for t in q & words) / total

        items = list(groups.values())
        if not items:
            return ""
        first = share(items[0])
        blocks: list[str] = []
        seen: set[str] = set()
        for n, parts in enumerate(items):
            if len(blocks) >= max_sections:
                break
            if n and share(parts) < max(0.34, 0.75 * first):
                continue
            budget = budgets[min(len(blocks), len(budgets) - 1)]
            lines = self._section_quote(parts, q, budget, max_table_rows if not blocks else 15, seen)
            if lines:
                blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _section_quote(self, parts: list[tuple[int, RetrievedChunk]], q: set[str], budget: int, max_rows: int,
                       seen: set[str], max_chars: int = 700) -> list[str]:
        anchor = parts[0][1]
        out: list[str] = []
        rows: list[str] = []
        label = ""
        more = False

        def flush() -> None:
            nonlocal rows
            if not rows:
                return
            labelled = [r for r in rows if all(_CELL_LABEL_RE.match(cell) for cell in r.split(" | "))]
            if len(labelled) * 2 >= len(rows):
                rows = labelled
            table = markdown_table(rows[:max_rows], q)
            out.extend(([""] if out else []) + (table if table else [f"- {r}" for r in rows[:max_rows]]))
            if len(rows) > max_rows:
                out.extend(["", f"Showing the first {max_rows} of {len(rows)} entries; the source page has the rest."])
            out.append("")
            rows = []

        for _, part in parts:
            for raw in part.text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                heading = re.match(r"^#{1,6}\s+(.+)$", line)
                if heading:
                    flush()
                    text = heading.group(1).strip()
                    label = "" if text in anchor.heading_path else text
                    continue
                key = re.sub(r"\W+", "", line.lower())  # "PhD" and "Ph.D." copies of one paragraph are one
                if key in seen:  # overlap between the pieces of a split section, or the same text on two pages
                    continue
                seen.add(key)
                if " | " in line:
                    rows.append(line)
                    continue
                flush()
                if sum(1 for x in out if x.startswith("- ")) >= budget:
                    more = True
                    continue
                line = re.sub(r"^[-*•]\s+", "", line)
                if len(line) > max_chars:
                    cut = line.rfind(". ", 0, max_chars)
                    line = line[:cut + 1 if cut > max_chars // 2 else max_chars].rstrip() + " …"
                out.append(f"- **{label}:** {line}" if label else f"- {line}")
                label = ""
        flush()
        while out and not out[-1]:
            out.pop()
        if not out:
            return []
        cites = "".join(f"[S{i}]" for i, _ in parts)
        if more:
            out.append("- … more on the source page.")
        return [f"**{source_label(anchor, q)}** {cites}", *out]

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
            # labelled rows ("Name: X | Designation: Y") repeat the header: drop the bare header line,
            # but only when the table is labelled - one cell mentioning "Note: ..." does not make it so
            labelled = [r for r in part_rows if all(_CELL_LABEL_RE.match(cell) for cell in r.split(" | "))]
            if len(labelled) * 2 >= len(part_rows):
                part_rows = labelled
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


def source_label(chunk: RetrievedChunk, q: set[str] | None = None) -> str:
    """ "Faculty List – Artificial Intelligence and Data Science": the page and its main section, and
    the sub-heading that names the question when there is one ("About Department – Civil
    Engineering – NBA Accredited from 2024 to 2027" for "Which departments are NBA accredited?")."""
    title = chunk.page_title.strip()
    section = chunk.heading_path[0].strip() if chunk.heading_path else ""
    label = title or section
    if section and section.lower() not in title.lower() and title.lower() not in section.lower():
        label = f"{title} – {section}"
    if q:
        named = [h for h in chunk.heading_path[1:] if q & set(tokenize(h)) and h.lower() not in label.lower()]
        if named:
            label = f"{label} – {named[-1].strip()}"
    return label


_CELL_LABEL_RE = re.compile(r"^\s*[^:|]{1,60}:\s")
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


class GeminiLLM:
    """Google Gemini (AI Studio API key; the free tier covers the Flash models)."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 8192, timeout: float = 90.0, client=None):
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout * 1000)))
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"gemini:{model}"

    async def generate(self, system: str, messages: list[dict]) -> LLMAnswer:
        from google.genai import errors, types

        contents = [types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
                    for m in messages]
        config = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=self.max_tokens, temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        try:
            response = await self.client.aio.models.generate_content(model=self.model, contents=contents, config=config)
        except errors.APIError as exc:
            code = getattr(exc, "code", 0)
            reason = {400: f"Gemini rejected the request: {exc.message}",
                      401: "Gemini authentication failed - check GEMINI_API_KEY",
                      403: "Gemini API key lacks permission (or the API is not enabled for it)",
                      404: f"Gemini model {self.model!r} not found - set GEMINI_MODEL",
                      429: "Gemini rate limit or free-tier quota reached"}.get(code, f"Gemini API error (HTTP {code})")
            raise LLMUnavailable(reason) from exc
        except Exception as exc:  # network errors from the HTTP client
            raise LLMUnavailable(f"Could not reach the Gemini API ({type(exc).__name__})") from exc

        blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        candidate = (response.candidates or [None])[0]
        finish = str(getattr(candidate, "finish_reason", "") or "")
        if blocked or finish.endswith(("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII")):
            return LLMAnswer(text="", model=self.model, refused=True)
        text = (response.text or "").strip()
        if not text:
            # e.g. RECITATION: Gemini stops when an answer repeats its sources word for word
            raise LLMUnavailable(f"Gemini returned no text ({finish or 'no candidates'})")
        if finish.endswith("MAX_TOKENS"):
            log.warning("LLM answer truncated at max_tokens=%s", self.max_tokens)
        return LLMAnswer(text=text, model=getattr(response, "model_version", None) or self.model)


def gemini_api_key(settings) -> str:
    return settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")


def get_llm(settings) -> LLMClient | None:
    """The configured answer model. "auto" (and "anthropic" without Anthropic credentials) uses
    Gemini when a GEMINI_API_KEY is set, so adding that one key is enough to switch."""
    provider = settings.llm_provider
    if provider == "extractive":
        return None
    gemini_key = gemini_api_key(settings)
    if provider in ("auto", "anthropic") and not anthropic_credentials_present() and gemini_key:
        if provider == "anthropic":
            log.info("No Anthropic credentials but GEMINI_API_KEY is set: answering with Gemini")
        provider = "gemini"
    try:
        if provider == "gemini":
            if not gemini_key:
                log.warning("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty; using extractive answers")
                return None
            return GeminiLLM(settings.gemini_model, gemini_key, min(settings.llm_max_tokens, 8192),
                             settings.llm_timeout_seconds)
        if not anthropic_credentials_present():
            log.warning("LLM_PROVIDER=%s but no Anthropic or Gemini credentials found; using extractive answers", provider)
            return None
        return AnthropicLLM(settings.llm_model, settings.llm_effort, settings.llm_max_tokens,
                            settings.llm_timeout_seconds, settings.llm_server_fallbacks)
    except Exception as exc:
        log.warning("Hosted LLM disabled: %s", exc)
        return None


__all__ = ["AnthropicLLM", "ExtractiveAnswerer", "GeminiLLM", "LLMAnswer", "LLMClient", "LLMUnavailable", "SYSTEM_PROMPT", "get_llm"]
