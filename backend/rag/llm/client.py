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


_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


class ExtractiveAnswerer:
    """No-LLM mode: quote the most query-relevant sentences from the top sources.

    Used when no API key is configured or the hosted LLM is unavailable. It can
    only repeat retrieved text, so it never invents facts.
    """

    name = "extractive"

    def answer(self, question: str, chunks: list[RetrievedChunk], max_sources: int = 3, per_source: int = 2) -> str:
        q = set(tokenize(question))
        lines: list[str] = []
        for i, chunk in enumerate(chunks[:max_sources], start=1):
            candidates = []
            for sentence in _SENT_RE.split(chunk.text):
                sentence = sentence.strip().lstrip("#").strip()
                if len(sentence) < 15:
                    continue
                overlap = len(q.intersection(tokenize(sentence)))
                if overlap:
                    candidates.append((overlap, sentence))
            candidates.sort(key=lambda c: -c[0])
            for _, sentence in candidates[:per_source]:
                lines.append(f"- {sentence} [S{i}]")
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
