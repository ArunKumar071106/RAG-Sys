from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from rag.llm.answer import NO_ANSWER_TEXT, AnswerService, ChatTurn, renumber_citations, sanitize_links
from rag.llm.client import AnthropicLLM, LLMAnswer, LLMUnavailable
from rag.llm.prompts import NO_ANSWER_MARKER, SYSTEM_PROMPT, build_context
from rag.models import RetrievedChunk, RetrievedImage


# ---------------------------------------------------------------- pure helpers
def test_renumber_citations_drops_invented_and_compacts():
    answer, s, i = renumber_citations("Fees are Rs. 60,000 [S3]. Hostel exists [S1][S9]. See [I2] .", 3, 2)
    assert answer == "Fees are Rs. 60,000 [S1]. Hostel exists [S2]. See [I1]."
    assert s == [3, 1] and i == [2]


def test_sanitize_links_keeps_only_retrieved_urls():
    allowed = {"https://aaaenggcoll.ac.in/admission"}
    text = ("See [admissions](https://aaaenggcoll.ac.in/admission) or [fake](https://evil.example/x) "
            "and https://made-up.example/page plus https://aaaenggcoll.ac.in/admission")
    out = sanitize_links(text, allowed)
    assert "evil.example" not in out and "made-up.example" not in out
    assert "[admissions](https://aaaenggcoll.ac.in/admission)" in out and "fake" in out


def test_context_labels_ai_descriptions_separately():
    chunk = RetrievedChunk(chunk_id="c", doc_id="d", url="u", page_title="P", heading_path=["H"], text="body", score=1)
    image = RetrievedImage(image_id="i", url="u", source_page="p", page_title="P", heading="H", alt="alt", caption="",
                           ocr_text="OCR", description="desc", description_model="m", width=1, height=1, score=1)
    ctx = build_context([chunk], [image])
    assert '<source id="S1"' in ctx and '<image id="I1"' in ctx
    assert "ocr_text: OCR" in ctx and "ai_description (generated, unverified): desc" in ctx
    assert NO_ANSWER_MARKER in SYSTEM_PROMPT


def test_extractive_answer_keeps_abbreviations_rows_and_skips_headings_and_duplicates():
    from rag.llm.client import ExtractiveAnswerer

    text = ("## Fee Structure\n\nProgramme: B.Tech Data Science | Tuition fee per year: Rs. 60,000\n\n"
            "- The tuition fee is payable in two instalments.\n\nThe tuition fee is payable in two instalments.")
    chunk = RetrievedChunk(chunk_id="c", doc_id="d", url="u", page_title="P", heading_path=[], text=text, score=1)
    answer = ExtractiveAnswerer().answer("tuition fee for data science", [chunk])
    assert answer.splitlines()[0] == "- Programme: B.Tech Data Science | Tuition fee per year: Rs. 60,000 [S1]"
    assert answer.count("instalments") == 1
    assert "Fee Structure" not in answer and "- - " not in answer


# ---------------------------------------------------------------- service with a fake LLM
class FakeLLM:
    name = "fake"

    def __init__(self, reply: str = "", refused=False, error: Exception | None = None):
        self.reply, self.refused, self.error = reply, refused, error
        self.calls = []

    async def generate(self, system, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return LLMAnswer(text=self.reply, model="fake-model", refused=self.refused)


def test_extractive_answer_quotes_a_table_across_its_chunks():
    from rag.llm.client import ExtractiveAnswerer

    def part(cid, rows, heading="AI&DS"):
        return RetrievedChunk(chunk_id=cid, doc_id="fac", url="https://c.example/fac/", page_title="Faculty List",
                              heading_path=[heading], text="\n".join(rows), score=1.0)

    chunks = [part("a", ["S.No: 1. | Name of the Faculty: Dr.M.Karuppasamy", "S.No: 2. | Name of the Faculty: Dr.Sugumar"]),
              part("b", ["S.No: 3. | Name of the Faculty: Dr.R.Prabhu"]),
              part("c", ["Research centre approved by Anna University for faculty."], heading="Research")]
    answer = ExtractiveAnswerer().answer("AI&DS faculty name", chunks)
    assert answer.splitlines() == ["- S.No: 1. | Name of the Faculty: Dr.M.Karuppasamy [S1]",
                                   "- S.No: 2. | Name of the Faculty: Dr.Sugumar [S1]",
                                   "- S.No: 3. | Name of the Faculty: Dr.R.Prabhu [S2]"]  # the table is the answer


def test_extractive_answer_prefers_the_table_whose_page_title_names_the_question():
    from rag.llm.client import ExtractiveAnswerer

    def part(cid, url, title, text):
        return RetrievedChunk(chunk_id=cid, doc_id=url, url=url, page_title=title, heading_path=["Electrical Engineering"],
                              text=text, score=1.0)

    chunks = [part("v", "https://c.example/eee/vision/", "Vision & Mission",
                   "Electrical engineering taught by eminent faculty with modern facilities."),
              part("f1", "https://c.example/eee/faculty-list/", "Faculty List", "S.N.: 1. | Name: Dr.C.Senthil Kumar"),
              part("f2", "https://c.example/eee/faculty-list/", "Faculty List", "S.N.: 2. | Name: Dr.R.Pon Vengatesh")]
    answer = ExtractiveAnswerer().answer("Electrical Engineering faculty", chunks)
    assert answer.splitlines() == ["- S.N.: 1. | Name: Dr.C.Senthil Kumar [S2]", "- S.N.: 2. | Name: Dr.R.Pon Vengatesh [S3]"]


def service(services, llm):
    return AnswerService(services.retriever, llm, top_k=4, image_top_k=3)


async def test_llm_answer_with_citations_sources_and_images(services):
    llm = FakeLLM("The B.Tech Data Science fee is Rs. 60,000 per year [S1]. See the notice [I1].")
    result = await service(services, llm).answer("What is the fee for B.Tech Data Science?")
    assert result.mode == "llm" and not result.insufficient_evidence
    assert result.sources[0].id == "S1" and result.sources[0].url.endswith("/admissions.html")
    assert result.images and result.images[0].id == "I1" and result.images[0].src.startswith("/api/images/")
    user_msg = llm.calls[0][-1]["content"]
    assert "<sources>" in user_msg and "<question>What is the fee for B.Tech Data Science?</question>" in user_msg


async def test_no_answer_marker_yields_no_answer_with_related_sources(services):
    llm = FakeLLM(f"{NO_ANSWER_MARKER}\nThe website does not cover this.")
    result = await service(services, llm).answer("What is the fee for B.Tech Data Science?")
    assert result.mode == "no_answer" and result.insufficient_evidence
    assert result.answer == NO_ANSWER_TEXT and result.sources == [] and result.images == []
    assert result.related_sources and result.related_sources[0].id == "R1"


async def test_no_retrieval_evidence_skips_llm(services):
    llm = FakeLLM("should not be called")
    result = await service(services, llm).answer("zzqx wvvy plorp")
    assert result.mode == "no_answer" and llm.calls == []


async def test_refusal_is_reported_without_answer(services):
    result = await service(services, FakeLLM(refused=True)).answer("What is the fee for B.Tech Data Science?")
    assert result.mode == "no_answer" and result.sources == []


async def test_llm_outage_falls_back_to_extractive(services):
    result = await service(services, FakeLLM(error=LLMUnavailable("down"))).answer("library timings")
    assert result.mode == "extractive" and "temporarily unavailable" in result.notice
    assert "8:00 AM to 8:00 PM" in result.answer and "[S1]" in result.answer


async def test_extractive_mode_without_llm(services):
    result = await service(services, None).answer("How many students were placed in 2025?")
    assert result.mode == "extractive"
    assert "212" in result.answer
    assert result.sources[0].url.endswith("/placements.html")


async def test_followup_question_uses_history_for_retrieval(services):
    svc = service(services, None)
    history = [ChatTurn(role="user", content="Tell me about the computer science department"),
               ChatTurn(role="assistant", content="It has labs.")]
    assert svc.retrieval_query("and its labs?", history) == "Tell me about the computer science department and its labs?"
    assert svc.retrieval_query("What is the hostel capacity?", history) == "What is the hostel capacity?"
    assert svc.retrieval_query("what about fees", history).startswith("Tell me about the computer science department")
    assert svc.retrieval_query("and its labs?", []) == "and its labs?"
    messages = svc._messages("q", "ctx", history)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]


# ---------------------------------------------------------------- Anthropic client adapter
def fake_response(text="Answer [S1]", stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5",
                           content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)])


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def fake_client(response=None, error=None):
    beta = FakeMessages(response, error)
    plain = FakeMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=beta), messages=plain), beta, plain


async def test_anthropic_llm_uses_server_fallbacks_and_effort():
    client, beta, plain = fake_client(fake_response())
    llm = AnthropicLLM("claude-opus-5-5", effort="low", client=client)
    answer = await llm.generate("sys", [{"role": "user", "content": "q"}])
    assert answer.text == "Answer [S1]" and not answer.refused
    assert beta.kwargs["fallbacks"] == "default" and beta.kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert beta.kwargs["output_config"] == {"effort": "low"} and beta.kwargs["model"] == "claude-opus-5-5"
    assert plain.kwargs is None


async def test_anthropic_llm_without_fallback_support_uses_plain_endpoint():
    client, beta, plain = fake_client(fake_response())
    await AnthropicLLM("claude-haiku-5-5", client=client).generate("sys", [])
    assert beta.kwargs is None and "fallbacks" not in plain.kwargs


async def test_anthropic_llm_refusal():
    client, _, _ = fake_client(fake_response("", stop_reason="refusal"))
    answer = await AnthropicLLM("claude-opus-5-5", client=client).generate("sys", [])
    assert answer.refused


@pytest.mark.parametrize("error", [
    anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")),
    anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=httpx2.Request("POST", "https://x")), body=None),
    anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=httpx2.Request("POST", "https://x")), body=None),
    anthropic.InternalServerError("boom", response=httpx2.Response(500, request=httpx2.Request("POST", "https://x")), body=None),
])
async def test_anthropic_llm_errors_become_unavailable(error):
    client, _, _ = fake_client(error=error)
    with pytest.raises(LLMUnavailable):
        await AnthropicLLM("claude-opus-5-5", client=client).generate("sys", [])


async def test_unrelated_page_images_only_when_question_asks_for_pictures(services):
    svc = service(services, None)
    plain = await svc.answer("What is the tuition fee for B.Tech Data Science?")
    cited_pages = {src.url for src in plain.sources}
    assert all(img.source_page in cited_pages for img in plain.images)
    photos = await svc.answer("Show me photos of the hostel")
    assert photos.images and any("hostel" in img.original_url for img in photos.images)
    cited = {src.url for src in photos.sources}
    on_cited = [img.source_page in cited for img in photos.images]
    assert on_cited == sorted(on_cited, reverse=True)  # images from cited pages come first
