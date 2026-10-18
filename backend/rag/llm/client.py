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
               max_lines: int = 6, max_table_rows: int = 12) -> str:
        q = set(tokenize(question))
        lines: list[str] = []
        seen: set[str] = set()
        for i, chunk in enumerate(chunks[:max_sources], start=1):
            candidates = []
            local: set[str] = set()
            sentences = self._sentences(chunk.text)
            for position, sentence in enumerate(sentences):
                key = re.sub(r"\W+", " ", sentence.lower()).strip()
                if len(sentence) < 15 or key in seen or key in local:
                    continue
                local.add(key)
                score = sum(self.term_weight(t) for t in q.intersection(tokenize(sentence)))
                if score > 0:
                    candidates.append((-score, position, key, sentence))
            candidates.sort()
            picked = candidates[:per_source]
            if picked and " | " in picked[0][3]:
                # a matching table row: quote the table's rows rather than one isolated line
                rows = [x for x in sentences if " | " in x][:max_table_rows]
                for row in rows:
                    key = re.sub(r"\W+", " ", row.lower()).strip()
                    if key not in seen:
                        seen.add(key)
                        lines.append(f"- {row} [S{i}]")
                picked = [c for c in picked if " | " not in c[3]]
            for _, _, key, sentence in picked:
                seen.add(key)
                lines.append(f"- {sentence} [S{i}]")
            if len(lines) >= max_lines:
                break
        return "\n".join(lines)


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
