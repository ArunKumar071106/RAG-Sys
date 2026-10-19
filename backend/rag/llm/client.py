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

    def answer(self, question: str, chunks: list[RetrievedChunk], max_sources: int = 3, per_source: int = 2,
               max_lines: int = 6, max_table_rows: int = 40) -> str:
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
                score = sum(self.term_weight(t) for t in q & (set(tokenize(sentence)) | title_terms))
                if score > 0 and q & set(tokenize(sentence)) or " | " in sentence and score > 0:
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
        if " | " in best[4]:
            # the table is the answer, with the best plain sentences from the same source as context
            lines = self._quote_table(chunks, chunks[best[1] - 1], max_table_rows)
            notes = [c for c in scored if c[1] == best[1] and " | " not in c[4]][:per_source]
            seen_notes: set[str] = set()
            for _, i, _, key, sentence in notes:
                if key not in seen_notes:
                    seen_notes.add(key)
                    lines.append(f"- {sentence} [S{i}]")
            return "\n".join(lines)

        lines: list[str] = []
        seen: set[str] = set()
        for i in range(1, min(max_sources, len(chunks)) + 1):
            for _, _, _, key, sentence in [c for c in scored if c[1] == i][:per_source]:
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- {sentence} [S{i}]")
            if len(lines) >= max_lines:
                break
        return "\n".join(lines)

    def _quote_table(self, chunks: list[RetrievedChunk], anchor: RetrievedChunk, max_rows: int) -> list[str]:
        """Every row of the anchor's table, across the sources that hold parts of it, in order."""
        section = (anchor.doc_id, anchor.heading_path)
        lines: list[str] = []
        seen: set[str] = set()
        for j, part in enumerate(chunks, start=1):
            if (part.doc_id, part.heading_path) != section:
                continue
            rows = [x for x in self._sentences(part.text) if " | " in x]
            if any(": " in r for r in rows):  # labelled rows repeat the header: drop the bare header line
                rows = [r for r in rows if ": " in r]
            for row in rows:
                key = re.sub(r"\W+", " ", row.lower()).strip()
                if key not in seen and len(lines) < max_rows:
                    seen.add(key)
                    lines.append(f"- {row} [S{j}]")
        return lines


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
