"""Grounded answer generation.

retrieve (hybrid text + images) -> evidence check -> prompt the LLM (or
extractive fallback) -> validate citations -> strip unknown links ->
return answer + cited official sources + relevant images.
"""

from __future__ import annotations

import logging
import re
import time
from html import escape
from typing import Literal

from pydantic import BaseModel, Field

from rag.index.bm25 import tokenize
from rag.llm.client import AnthropicLLM, ExtractiveAnswerer, LLMUnavailable
from rag.llm.language import is_english
from rag.llm.prompts import (ANSWER_TRANSLATE_PROMPT, CONTEXT_PROMPT, NO_ANSWER_MARKER, SYSTEM_PROMPT, TRANSLATE_PROMPT,
                             build_context, build_user_message)
from rag.models import RetrievedChunk, RetrievedImage
from rag.retrieval.hybrid import HybridRetriever, expand_query
from rag.retrieval.suggest import department_in

log = logging.getLogger(__name__)

NO_ANSWER_TEXT = (
    "I couldn't find this in the official AAACET website content I have access to. "
    "Please check the official website or contact the college office directly."
)
_CITATION_RE = re.compile(r"\[(S|I)(\d+)\]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"(?<![(\[])https?://[^\s)\]]+")
_WANTS_IMAGES_RE = re.compile(
    r"\b(photos?|pictures?|pics?|images?|gallery|posters?|notices?|brochures?|show me|look(s)? like|view of)\b", re.I
)
_DEPARTMENT_WORDS = {"lab", "labs", "laboratory", "laboratories", "faculty", "faculties", "staff", "hod", "head", "syllabus",
                     "curriculum", "vision", "mission", "achievements", "intake", "seats", "professor", "professors",
                     "teachers", "events", "association", "courses", "course", "toppers", "results"}
_FOLLOWUP_RE = re.compile(
    r"^\s*(and|also|then|so|what about|how about|same for)\b|\b(it|its|it's|they|them|their|those|these|that one|he|she|his|her)\b",
    re.I,
)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class SourceOut(BaseModel):
    id: str
    chunk_id: str
    title: str
    url: str
    heading: str
    snippet: str
    score: float


class ImageOut(BaseModel):
    id: str
    image_id: str
    src: str  # served by this API
    original_url: str
    source_page: str
    page_title: str
    heading: str
    alt: str
    caption: str
    ocr_text: str
    description: str
    description_is_ai_generated: bool
    width: int
    height: int


class ChatResult(BaseModel):
    answer: str
    mode: Literal["llm", "extractive", "no_answer"]
    insufficient_evidence: bool
    sources: list[SourceOut] = Field(default_factory=list)
    related_sources: list[SourceOut] = Field(default_factory=list)
    images: list[ImageOut] = Field(default_factory=list)
    notice: str = ""
    model: str = ""
    timings_ms: dict[str, int] = Field(default_factory=dict)
    # Not in English and an AI service is set up, so POST /api/translate can give an English version.
    translatable: bool = False
    # Full questions to offer next, about the same department or related topics.
    follow_ups: list[str] = Field(default_factory=list)


def _snippet(text: str, limit: int = 240) -> str:
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def source_out(index: int, chunk: RetrievedChunk) -> SourceOut:
    return SourceOut(id=f"S{index}", chunk_id=chunk.chunk_id, title=chunk.page_title, url=chunk.url,
                     heading=" > ".join(chunk.heading_path), snippet=_snippet(chunk.text), score=chunk.score)


def image_out(index: int, image: RetrievedImage) -> ImageOut:
    return ImageOut(id=f"I{index}", image_id=image.image_id, src=f"/api/images/{image.image_id}/file",
                    original_url=image.url, source_page=image.source_page, page_title=image.page_title,
                    heading=image.heading, alt=image.alt, caption=image.caption, ocr_text=image.ocr_text,
                    description=image.description, description_is_ai_generated=bool(image.description),
                    width=image.width, height=image.height)


def sanitize_links(answer: str, allowed_urls: set[str]) -> str:
    """Remove any URL the model wrote that is not one of the retrieved official URLs."""
    def md(match: re.Match) -> str:
        return match.group(0) if match.group(2) in allowed_urls else match.group(1)

    answer = _MD_LINK_RE.sub(md, answer)
    return _BARE_URL_RE.sub(lambda m: m.group(0) if m.group(0) in allowed_urls else "", answer)


def renumber_citations(answer: str, n_sources: int, n_images: int) -> tuple[str, list[int], list[int]]:
    """Drop citations to non-existent evidence and renumber the rest compactly.

    Returns the rewritten answer and the original (1-based) indices of cited
    sources and images, in order of first citation.
    """
    cited_s: list[int] = []
    cited_i: list[int] = []
    for kind, num in _CITATION_RE.findall(answer):
        n = int(num)
        if kind == "S" and 1 <= n <= n_sources and n not in cited_s:
            cited_s.append(n)
        if kind == "I" and 1 <= n <= n_images and n not in cited_i:
            cited_i.append(n)

    def repl(match: re.Match) -> str:
        kind, n = match.group(1), int(match.group(2))
        order = cited_s if kind == "S" else cited_i
        return f"[{kind}{order.index(n) + 1}]" if n in order else ""

    answer = _CITATION_RE.sub(repl, answer)
    answer = re.sub(r"[ \t]+([.,;:])", r"\1", answer)
    return answer.strip(), cited_s, cited_i


class AnswerService:
    def __init__(self, retriever: HybridRetriever, llm: AnthropicLLM | None, history_turns: int = 6,
                 top_k: int = 6, image_top_k: int = 4):
        self.retriever = retriever
        self.llm = llm
        idf = getattr(getattr(retriever.bm25_text, "_bm25", None), "idf", None) or {}
        floor = max(idf.values(), default=1.0)
        self.extractive = ExtractiveAnswerer(lambda t: max(idf.get(t, floor), 0.05))
        self.history_turns = history_turns
        self.top_k = top_k
        self.image_top_k = image_top_k

    def retrieval_query(self, question: str, history: list[ChatTurn]) -> str:
        """What to search for a question that may lean on the previous one (without an LLM):
        "what about its labs?" after a CSE question searches CSE labs, "and ECE?" after "faculty of
        CSE" searches ECE faculty, and other follow-ups ("what about fees?") borrow the previous question."""
        previous = next((t.content for t in reversed(history) if t.role == "user"), "")
        if not previous:
            return question
        settings = self.retriever.settings
        asked = self.retriever.normalize_query(question)
        followup = bool(_FOLLOWUP_RE.search(question)) and len(tokenize(question)) <= 10 or not tokenize(asked)
        # "labs?", "and the HOD?" right after a department question are about that department
        short = len(tokenize(asked)) <= 3 and bool(set(tokenize(asked)) & _DEPARTMENT_WORDS)
        now, before = department_in(question, settings), department_in(previous, settings)
        if now and before and now != before and followup:
            # same request about another department: the earlier question, with the department swapped
            earlier = expand_query(previous, settings.query_expansions)
            swapped = re.sub(re.escape(before), now, earlier, count=1, flags=re.I)
            if swapped != earlier:
                return swapped
            dept_words = set(tokenize(before))
            intent = " ".join(w for w in tokenize(self.retriever.normalize_query(previous)) if w not in dept_words)
            return f"{question} {intent}".strip()
        if before and not now and (followup or short):
            return f"{question} {before}"
        return f"{previous} {question}" if followup else question

    def _messages(self, question: str, context: str, history: list[ChatTurn]) -> list[dict]:
        turns = [t for t in history if t.content.strip()][-self.history_turns * 2:]
        while turns and turns[0].role != "user":
            turns = turns[1:]
        messages: list[dict] = []
        for turn in turns:
            if messages and messages[-1]["role"] == turn.role:
                messages[-1]["content"] += "\n\n" + turn.content[:2000]
            else:
                messages.append({"role": turn.role, "content": turn.content[:2000]})
        if messages and messages[-1]["role"] == "user":
            messages.append({"role": "assistant", "content": "(previous question noted)"})
        messages.append({"role": "user", "content": build_user_message(question, context)})
        return messages

    async def search_query(self, question: str, history: list[ChatTurn]) -> str:
        """The English query to search the website with. With an LLM, a follow-up is rewritten into
        a standalone question using the earlier ones, and other languages are translated; without
        one, follow-ups borrow from the previous question and the rest is searched as written."""
        query = self.retrieval_query(question, history)
        earlier = [t.content[:300] for t in history if t.role == "user" and t.content.strip()][-3:]
        if self.llm is None or (is_english(question) and not earlier):
            return query
        if earlier:
            listed = "\n".join(f"- {escape(q)}" for q in earlier)
            prompt, content = CONTEXT_PROMPT, f"<conversation>\n{listed}\n</conversation>\n<question>{escape(question)}</question>"
        else:
            prompt, content = TRANSLATE_PROMPT, f"<question>{escape(query)}</question>"
        try:
            result = await self.llm.generate(prompt, [{"role": "user", "content": content}])
        except LLMUnavailable as exc:
            log.warning("Could not rewrite the question for searching: %s", exc)
            return query
        rewritten = result.text.strip().splitlines()[0].strip() if result.text.strip() and not result.refused else ""
        return rewritten or query

    async def translate(self, text: str, language: str = "English") -> str:
        """An answer in another language (for the "Show in English" button); links stay official."""
        if self.llm is None:
            raise LLMUnavailable("No AI answer service is configured")
        result = await self.llm.generate(ANSWER_TRANSLATE_PROMPT.format(language=language),
                                         [{"role": "user", "content": f"<answer>\n{text}\n</answer>"}])
        if result.refused or not result.text.strip():
            raise LLMUnavailable("The translation was not returned")
        allowed = set(re.findall(r"https?://[^\s)\]>]+", text))
        return sanitize_links(result.text.strip(), allowed)

    async def answer(self, question: str, history: list[ChatTurn] | None = None) -> ChatResult:
        result = await self._answer(question, history or [])
        # an AI answer in the question's language can be shown in English on request
        result.translatable = self.llm is not None and result.mode != "extractive" and not is_english(result.answer)
        return result

    async def _answer(self, question: str, history: list[ChatTurn]) -> ChatResult:
        timings: dict[str, int] = {}
        t0 = time.perf_counter()
        query = await self.search_query(question, history)
        text = self.retriever.search_text(query, self.top_k)
        images = self.retriever.search_images(query, self.image_top_k, text.chunks) if text.chunks else []
        timings["retrieval"] = int((time.perf_counter() - t0) * 1000)

        language_notice = "" if self.llm is not None or is_english(question) else (
            "Questions in other languages are answered in English quotes; set up the AI answer service"
            " (ANTHROPIC_API_KEY) to ask and get answers in any language.")
        if not text.chunks:
            return ChatResult(answer=NO_ANSWER_TEXT, mode="no_answer", insufficient_evidence=True, notice=language_notice,
                              timings_ms=timings)
        text.chunks = self.retriever.expand_section(text.chunks)

        sources_all = [source_out(i, c) for i, c in enumerate(text.chunks, start=1)]
        images_all = [image_out(i, im) for i, im in enumerate(images, start=1)]
        allowed_urls = {c.url for c in text.chunks} | {im.url for im in images} | {im.source_page for im in images}

        notice = ""
        model = ""
        raw = ""
        mode: Literal["llm", "extractive", "no_answer"] = "llm"
        t1 = time.perf_counter()
        if self.llm is not None:
            try:
                result = await self.llm.generate(SYSTEM_PROMPT, self._messages(question, build_context(text.chunks, images), history))
                model = result.model
                if result.refused:
                    return ChatResult(answer="I can't help with that request. Please ask about AAACET's admissions, courses, "
                                      "facilities or other college information.", mode="no_answer", insufficient_evidence=True,
                                      model=model, timings_ms=timings)
                raw = result.text
            except LLMUnavailable as exc:
                log.warning("LLM unavailable, falling back to extractive answer: %s", exc)
                notice = "The AI answer service is temporarily unavailable, so this answer quotes the official website directly."
                mode = "extractive"
        else:
            mode = "extractive"
            notice = " ".join(filter(None, ["Answers quote the official website directly (AI answer generation is not configured).",
                                            language_notice]))
        if mode == "extractive":
            raw = self.extractive.answer(self.retriever.normalize_query(query), text.chunks)
        timings["generation"] = int((time.perf_counter() - t1) * 1000)

        if not raw.strip() or raw.lstrip().startswith(NO_ANSWER_MARKER):
            # the model's own "not covered" sentence is in the question's language
            said = raw.replace(NO_ANSWER_MARKER, "").strip() if mode == "llm" and not is_english(question) else ""
            return ChatResult(answer=said or NO_ANSWER_TEXT, mode="no_answer", insufficient_evidence=True,
                              related_sources=[r.model_copy(update={"id": f"R{n}"}) for n, r in enumerate(sources_all[:3], start=1)],
                              model=model, notice=notice, timings_ms=timings)

        answer = sanitize_links(raw.replace(NO_ANSWER_MARKER, "").strip(), allowed_urls)
        answer, cited_s, cited_i = renumber_citations(answer, len(sources_all), len(images_all))
        if not cited_s:
            # The model answered without citing: show what it was given, never nothing.
            cited_s = list(range(1, min(3, len(sources_all)) + 1))
        sources = []
        for new_idx, orig in enumerate(cited_s, start=1):
            sources.append(sources_all[orig - 1].model_copy(update={"id": f"S{new_idx}"}))
        cited_pages = {s.url for s in sources}

        # Images the answer cites, then images from the cited pages; images from other pages
        # only when the question asks for pictures ("show me photos of ...").
        wants_images = bool(_WANTS_IMAGES_RE.search(question))
        chosen_images = [images_all[i - 1] for i in cited_i]
        from_cited_pages = [im for im in images_all if im.source_page in cited_pages]
        others = [im for im in images_all if im.source_page not in cited_pages] if wants_images else []
        for image in from_cited_pages + others:
            if len(chosen_images) >= self.image_top_k:
                break
            if image not in chosen_images:
                chosen_images.append(image)
        chosen_images = [im.model_copy(update={"id": f"I{n}"}) for n, im in enumerate(chosen_images, start=1)]

        return ChatResult(answer=answer, mode=mode, insufficient_evidence=False, sources=sources, images=chosen_images,
                          related_sources=[r.model_copy(update={"id": f"R{n}"}) for n, r in enumerate(
                              [s for s in sources_all if s.chunk_id not in {x.chunk_id for x in sources}][:3], start=1)],
                          notice=notice, model=model, timings_ms=timings)
