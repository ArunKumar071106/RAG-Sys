from pathlib import Path

from rag.config import BACKEND_DIR
from rag.eval.retrieval_eval import evaluate, load_questions, recall_at_k, reciprocal_rank, unique_urls


def test_hybrid_text_search_finds_table_fact(services):
    result = services.retriever.search_text("tuition fee for B.Tech Data Science", 3)
    top = result.chunks[0]
    assert top.url.endswith("/admissions.html")
    assert "Rs. 60,000" in top.text
    assert top.bm25_rank is not None and top.semantic_rank is not None  # fused from both retrievers
    assert len({c.chunk_id for c in result.chunks}) == len(result.chunks)


def test_semantic_only_hits_below_floor_are_dropped(services):
    result = services.retriever.search_text("zzqx wvvy plorp", 5)
    assert result.chunks == []


def test_image_retrieval_uses_ocr_text(services):
    # the poster has no alt text: only OCR can find it
    images = services.retriever.search_images("robotics engineering scholarship test helpline", 3)
    assert images and images[0].url.endswith("admission-notice.png")
    assert "HELPLINE" in images[0].ocr_text.upper()


def test_image_retrieval_by_alt_and_caption(services):
    text = services.retriever.search_text("computer laboratory systems", 3)
    images = services.retriever.search_images("computer laboratory systems", 3, text.chunks)
    assert images[0].url.endswith("computer-lab.jpg")
    assert images[0].source_page.endswith("/departments/computer-science.html")


def test_irrelevant_query_returns_no_images(services):
    assert services.retriever.search_images("quantum chromodynamics lecture", 3) == []


def test_metric_functions():
    urls = ["https://x/a", "https://x/b", "https://x/c"]
    assert recall_at_k(urls, ["/b", "/z"], 2) == 0.5
    assert recall_at_k(urls, ["/b"], 1) == 0.0
    assert reciprocal_rank(urls, ["/c"]) == 1 / 3
    assert reciprocal_rank(urls, ["re:/(a|b)$"]) == 1.0
    assert reciprocal_rank(urls, ["/q"]) == 0.0
    assert unique_urls(["a", "b", "a"]) == ["a", "b"]


def test_retrieval_quality_on_demo_questions(services):
    """Recall@K / MRR on labelled questions with expected source pages."""
    questions = load_questions(Path(BACKEND_DIR / "eval" / "questions_demo.jsonl"))
    report = evaluate(services.retriever, questions, k_values=(1, 3, 5))
    summary = report.summary()
    assert summary["recall@5"] >= 0.9, summary
    assert summary["mrr"] >= 0.75, summary
    assert summary["image_hit"] == 1.0, summary
    assert summary["unanswerable_rejected"] == 1.0, summary


def test_news_posts_rank_below_official_pages_on_ties(services, monkeypatch):
    retriever = services.retriever
    monkeypatch.setattr(retriever.settings, "title_rank_weight", 0.0)  # isolate the page-type prior
    query = "college"  # appears on most demo pages, so there are several candidates
    before = retriever.search_text(query, 3).chunks
    assert len(before) >= 2
    top = before[0].chunk_id
    original = retriever.corpus.chunks[top].metadata.get("kind", "page")
    weights = dict(retriever.settings.kind_weights)
    try:
        retriever.corpus.chunks[top].metadata["kind"] = "news"
        retriever.settings.kind_weights = {**weights, "news": 0.5}
        after = retriever.search_text(query, 10).chunks
        ranked = [c.chunk_id for c in after]
        assert after[0].chunk_id != top  # an official page now leads
        assert top in ranked and ranked.index(top) > 0  # the news post is demoted, not removed
    finally:
        retriever.corpus.chunks[top].metadata["kind"] = original
        retriever.settings.kind_weights = weights


def test_request_words_are_not_treated_as_topic():
    from rag.retrieval.hybrid import content_query

    assert content_query("Show me photos of the hostel") == "of the hostel"
    assert content_query("What does the library look like?") == "What does the library ?"
    assert content_query("Show photos") == "Show photos"  # nothing topical left: keep the original


def test_title_field_ranking_finds_pages_by_their_title(services, monkeypatch):
    retriever = services.retriever
    # Leave only the title/headings ranking: the other retrievers find nothing.
    monkeypatch.setattr(retriever.bm25_text, "search", lambda query, limit: [])
    monkeypatch.setattr(retriever.store, "search", lambda collection, vector, limit: [])
    monkeypatch.setattr(retriever.settings, "title_rank_weight", 0.0)
    assert retriever.search_text("Contact Us", 3).chunks == []
    monkeypatch.setattr(retriever.settings, "title_rank_weight", 0.5)
    chunks = retriever.search_text("Contact Us", 3).chunks
    assert chunks and chunks[0].url.endswith("/contact.html")


def test_best_match_brings_the_rest_of_its_section(tmp_path):
    from rag.index.bm25 import BM25Index
    from rag.models import RetrievedChunk, TextChunk
    from rag.retrieval.corpus import Corpus
    from rag.retrieval.hybrid import HybridRetriever
    from tests.conftest import make_settings

    def chunk(cid, i, heading):
        return TextChunk(chunk_id=cid, doc_id="faculty", url="https://c.example/ai-dept/faculty-list/", page_title="Faculty List",
                         heading_path=[heading], text=f"S.No: {i}. | Name of the Faculty: Dr.X{i}", token_count=10,
                         chunk_index=i, content_hash=cid)

    corpus = Corpus(chunks={c.chunk_id: c for c in [chunk("t0", 0, "AI&DS"), chunk("t1", 1, "AI&DS"), chunk("t2", 2, "AI&DS"),
                                                     chunk("other", 3, "Research")]})
    corpus.sections = {("faculty", ("AI&DS",)): ["t0", "t1", "t2"], ("faculty", ("Research",)): ["other"]}
    retriever = HybridRetriever(make_settings(tmp_path / "data"), None, None, corpus, BM25Index([], []), BM25Index([], []))

    def hit(cid):
        c = corpus.chunks[cid]
        return RetrievedChunk(chunk_id=cid, doc_id=c.doc_id, url=c.url, page_title=c.page_title, heading_path=c.heading_path,
                              text=c.text, score=1.0)

    expanded = retriever.expand_section([hit("t1"), hit("other")])
    assert [c.chunk_id for c in expanded] == ["t0", "t1", "t2", "other"]  # page order, other results after
    assert [c.chunk_id for c in retriever.expand_section([hit("t1"), hit("other")], max_chunks=2)] == ["t1", "t2", "other"]
    assert [c.chunk_id for c in retriever.expand_section([hit("other"), hit("t1")])] == ["other", "t1"]  # single-chunk section


def test_labelled_facts_phrases_and_rare_terms():
    from rag.index.bm25 import BM25Index, tokenize
    from rag.retrieval.hybrid import labelled_fact_hits, query_phrases

    q = set(tokenize("What is the TNEA counselling code?"))
    assert labelled_fact_hits("COUNSELLING CODE : 4680\nAddress: Amathur", q) == 1
    assert labelled_fact_hits("DEPARTMENT: IT | INTAKE: 60\nDEPARTMENT: AI | INTAKE: 120", set(tokenize("intake for IT"))) == 1
    assert labelled_fact_hits("Note: the code of conduct", q) == 0  # "note" is not asked about
    assert query_phrases("What is the TNEA counselling code of AAACET?") == ["tnea counselling", "counselling code"]
    index = BM25Index.build([("a", "intake table"), ("b", "data science lab"), ("c", "data science news"), ("d", "data")])
    assert index.rare_terms("intake for data science", 1) == ["intake"]
    assert index.rare_terms("intake", 1) == []  # a one-word question is its own rare term


def test_query_normalising_department_and_intent_words(services):
    norm = services.retriever.normalize_query
    assert "department" not in norm("Who are the faculty of the Civil Engineering department?").lower()
    assert "department" in norm("Tell me about the Civil Engineering department").lower()  # the topic itself
    assert norm("Where is the college located?").endswith("address")
    assert "intake" in norm("How many seats are there in ECE?")
    assert "available" not in norm("What hostel facilities are available?")


def test_only_tables_are_completed_with_the_rest_of_their_section(tmp_path):
    from rag.index.bm25 import BM25Index
    from rag.models import RetrievedChunk, TextChunk
    from rag.retrieval.corpus import Corpus
    from rag.retrieval.hybrid import HybridRetriever
    from tests.conftest import make_settings

    def chunk(cid, i):
        return TextChunk(chunk_id=cid, doc_id="naac", url="https://c.example/naac/", page_title="NAAC", heading_path=["Criteria"],
                         text=f"Criterion {i} is described in the self study report.", token_count=10, chunk_index=i, content_hash=cid)

    corpus = Corpus(chunks={c.chunk_id: c for c in [chunk("p0", 0), chunk("p1", 1), chunk("p2", 2)]})
    corpus.sections = {("naac", ("Criteria",)): ["p0", "p1", "p2"]}
    retriever = HybridRetriever(make_settings(tmp_path / "data"), None, None, corpus, BM25Index([], []), BM25Index([], []))
    c = corpus.chunks["p1"]
    hit = RetrievedChunk(chunk_id="p1", doc_id=c.doc_id, url=c.url, page_title=c.page_title, heading_path=c.heading_path,
                         text=c.text, score=1.0)
    # a long prose section is not pulled in: it would push the result that answers out of the top sources
    assert [r.chunk_id for r in retriever.expand_section([hit])] == ["p1"]



def test_remote_store_searches_images_alongside_text_with_one_embedding(services, monkeypatch):
    """Over the network the image search starts with the text search; the question is embedded once."""
    import threading

    from rag.retrieval.hybrid import HybridRetriever

    base = services.retriever
    store, embedder = base.store, base.embedder
    monkeypatch.setattr(store, "remote", True)
    parts = (base.settings, embedder, store, base.corpus, base.bm25_text, base.bm25_images)
    retriever = HybridRetriever(*parts)
    embedded, threads = [], set()
    real_embed, real_search = embedder.embed_query, store.search
    monkeypatch.setattr(embedder, "embed_query", lambda q: embedded.append(q) or real_embed(q))
    monkeypatch.setattr(store, "search", lambda *a, **k: threads.add(threading.current_thread().name) or real_search(*a, **k))
    query = "campus map"
    images = retriever.search_images(query, 3, retriever.search_text(query).chunks)
    assert len(embedded) == 1 and any(t.startswith("qdrant") for t in threads)
    sequential = HybridRetriever(*parts)
    sequential._pool = None
    expected = sequential.search_images(query, 3, sequential.search_text(query).chunks)
    assert images and [i.image_id for i in images] == [i.image_id for i in expected]


def test_parent_overview_goes_before_its_subsections():
    from types import SimpleNamespace

    from rag.models import RetrievedChunk
    from rag.retrieval.hybrid import HybridRetriever

    overview = SimpleNamespace(chunk_id="o", doc_id="t", url="https://c.example/transport/", page_title="Transport",
                               heading_path=["Transport Facilities"], text="12 buses run up to 70 kms.")
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.corpus = SimpleNamespace(sections={("t", ("Transport Facilities",)): ["o"]}, chunks={"o": overview})

    def route(name):
        return RetrievedChunk(chunk_id=name, doc_id="t", url=overview.url, page_title="Transport",
                              heading_path=["Transport Facilities", f"{name} Bus Route"], text="Boarding Point: X", score=1)

    routes = [route("Madurai"), route("Kovilpatti")]
    assert [c.chunk_id for c in retriever.with_parent_overview(routes)] == ["o", "Madurai", "Kovilpatti"]
    assert retriever.with_parent_overview(routes[:1]) == routes[:1]  # one subsection: it is the answer


def test_why_choose_questions_search_for_the_colleges_strengths(services):
    for question in ("Why should I choose this college?", "why join AAACET", "what is special about this college"):
        assert "NAAC" in services.retriever.normalize_query(question)
    assert "NAAC" not in services.retriever.normalize_query("Which hostel rooms are available?")
