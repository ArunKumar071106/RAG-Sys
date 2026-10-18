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
