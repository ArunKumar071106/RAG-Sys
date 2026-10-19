import numpy as np
import pytest

from rag.embeddings.base import BgeM3Embedder, HashingEmbedder, get_embedder
from rag.index.bm25 import BM25Index, tokenize
from rag.retrieval.rrf import reciprocal_rank_fusion


# ---------------------------------------------------------------- embeddings
def test_hashing_embedder_is_deterministic_and_normalised():
    emb = HashingEmbedder(256)
    a = emb.embed_documents(["Hostel facilities for students", "Library timings"])
    b = emb.embed_documents(["Hostel facilities for students", "Library timings"])
    assert a.shape == (2, 256) and a.dtype == np.float32
    assert np.allclose(a, b)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-5)
    assert emb.embed_documents([]).shape == (0, 256)


def test_hashing_embedder_similarity_follows_overlap():
    emb = HashingEmbedder(1024)
    q = emb.embed_query("hostel facilities")
    near, far = emb.embed_documents(["The hostel has excellent facilities", "Placement statistics for 2025"])
    assert float(q @ near) > float(q @ far)


def test_bge_m3_wrapper_normalises_and_reports_dimension():
    class FakeModel:
        def get_sentence_embedding_dimension(self):
            return 1024

        def encode(self, texts, batch_size, normalize_embeddings, show_progress_bar):
            assert normalize_embeddings is True
            return np.ones((len(texts), 1024)) / np.sqrt(1024)

    emb = BgeM3Embedder(model=FakeModel())
    assert emb.dim == 1024 and emb.name == "bge-m3:BAAI/bge-m3"
    assert emb.embed_query("x").shape == (1024,)


def test_get_embedder_selects_provider(settings):
    settings.embedding_provider = "hashing"
    assert isinstance(get_embedder(settings), HashingEmbedder)


def test_bge_m3_falls_back_to_fastembed_then_hashing(settings, monkeypatch):
    import rag.embeddings.base as emb

    def missing(*args, **kwargs):
        raise emb.MissingMLExtras("sentence-transformers not installed")

    class FakeFastEmbed:
        def __init__(self, *args, **kwargs):
            self.name, self.dim = "fastembed:fake", 3

    monkeypatch.setattr(emb, "BgeM3Embedder", missing)
    monkeypatch.setattr(emb, "FastEmbedEmbedder", FakeFastEmbed)
    settings.embedding_provider = "bge-m3"
    assert isinstance(get_embedder(settings), FakeFastEmbed)

    def offline(*args, **kwargs):
        raise ValueError("Could not load model from any source")

    monkeypatch.setattr(emb, "FastEmbedEmbedder", offline)
    assert isinstance(get_embedder(settings), HashingEmbedder)


def test_fastembed_wrapper_uses_query_prefix_and_normalises():
    from rag.embeddings.base import FastEmbedEmbedder

    class FakeModel:
        def embed(self, texts):
            return (np.array([3.0, 4.0]) for _ in texts)

        def query_embed(self, texts):
            return (np.array([0.0, 2.0]) for _ in texts)

    emb = FastEmbedEmbedder("BAAI/bge-base-en-v1.5", model=FakeModel())
    assert emb.dim == 2 and emb.name == "fastembed:BAAI/bge-base-en-v1.5"
    assert np.allclose(emb.embed_documents(["a", "b"]), [[0.6, 0.8], [0.6, 0.8]])
    assert np.allclose(emb.embed_query("q"), [0.0, 1.0])


# ---------------------------------------------------------------- BM25
def test_tokenize_handles_degrees_stopwords_and_plurals():
    assert tokenize("What are the B.E. courses?") == ["be", "course"]
    assert tokenize("Ph.D facilities") == ["phd", "facility"]
    assert tokenize("buses classes campus") == ["bus", "class", "campus"]


def test_tokenize_splits_words_glued_to_abbreviations():
    assert tokenize("B.E.COURSES") == ["be", "course"]  # heading written without a space
    assert tokenize("B.Tech M.Phil U.S.A") == ["btech", "mphil", "usa"]
    assert tokenize("enquiry@aaacet.ac.in") == ["enquiry", "aaacet", "ac"]
    assert tokenize("Dr.M.Sekar") == tokenize("Dr. M. Sekar") == ["dr", "m", "sekar"]


def test_bm25_ranks_and_persists_as_json(tmp_path):
    index = BM25Index.build([("a", "Hostel for boys and girls"), ("b", "Library opens at 8 AM"), ("c", "Bus transport routes")])
    assert index.search("library timings", 3)[0][0] == "b"
    assert index.search("quantum chromodynamics", 3) == []
    assert index.search("the and of", 3) == []
    path = tmp_path / "bm25.json"
    index.save(path)
    assert path.read_text().startswith("{")
    loaded = BM25Index.load(path)
    assert loaded.search("hostel", 1)[0][0] == "a"
    assert len(BM25Index.load(tmp_path / "missing.json")) == 0


# ---------------------------------------------------------------- RRF
def test_rrf_scores_and_order():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "d"]], k=60)
    scores = dict(fused)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert [x for x, _ in fused][:2] == ["b", "c"]
    assert scores["d"] == pytest.approx(1 / 63)


def test_rrf_weights_duplicates_and_validation():
    fused = dict(reciprocal_rank_fusion([["a", "a", "b"], ["b"]], k=0, weights=[1.0, 2.0]))
    assert fused["a"] == pytest.approx(1.0)  # duplicate in one list counted once
    assert fused["b"] == pytest.approx(1 / 3 + 2.0)
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], weights=[1, 2])
    assert reciprocal_rank_fusion([]) == []


def test_coverage_weights_rare_terms():
    index = BM25Index.build([("a", "college hostel for boys"), ("b", "college library"), ("c", "college bus"), ("d", "college canteen")])
    assert index.coverage("hostel college", "a") == pytest.approx(1.0)
    assert index.coverage("hostel college", "b") < 0.2  # only the common word matches
    assert index.coverage("moon college", "a") < 0.2  # unseen terms carry the most weight
    assert index.weighted_overlap("contact details", "Contact Us") > 0
