import numpy as np
import pytest
from qdrant_client import QdrantClient

from rag.embeddings.base import HashingEmbedder
from rag.index.indexer import Indexer, manifest_path
from rag.index.qdrant_store import QdrantStore, VectorDimensionMismatch
from rag.models import ImageChunk, TextChunk
from rag.utils import read_json, write_jsonl


@pytest.fixture
def store():
    s = QdrantStore(QdrantClient(location=":memory:"))
    yield s
    s.close()


def test_store_upsert_search_delete(store):
    store.ensure_collection("t", 4)
    vecs = np.eye(4, dtype=np.float32)
    store.upsert("t", ["a", "b", "c"], vecs[:3], [{"chunk_id": c, "doc_id": d} for c, d in [("a", "d1"), ("b", "d1"), ("c", "d2")]])
    assert store.count("t") == 3
    assert store.search("t", vecs[1], 1)[0][0] == "b"
    assert store.get("t", "c")["doc_id"] == "d2"
    store.delete_by_field("t", "doc_id", ["d1"])
    assert store.count("t") == 1
    store.delete_ids("t", ["c"])
    assert store.count("t") == 0
    assert store.search("missing", vecs[0], 3) == [] and store.count("missing") == 0


def test_dimension_mismatch_is_rejected_unless_recreated(store):
    store.ensure_collection("t", 4)
    with pytest.raises(VectorDimensionMismatch):
        store.ensure_collection("t", 8)
    store.ensure_collection("t", 8, recreate=True)
    assert store.collection_dim("t") == 8


def chunk(doc, i, text):
    return TextChunk(chunk_id=f"{doc}-{i}-{abs(hash(text)) % 10_000}", doc_id=doc, url=f"https://c.example/{doc}",
                     page_title=doc, text=text, token_count=5, chunk_index=i, content_hash=str(hash(text)))


def test_incremental_indexing_only_touches_changed_documents(settings, store):
    settings.ensure_dirs()
    embedder = HashingEmbedder(64)
    write_jsonl(settings.chunks_file, [chunk("a", 0, "hostel text"), chunk("b", 0, "library text")])
    write_jsonl(settings.image_chunks_file, [ImageChunk(chunk_id="i1", image_id="i1", url="u", source_page="p", page_title="t",
                                                        heading="h", text="hostel photo", content_hash="1")])
    indexer = Indexer(settings, embedder, store)
    first = indexer.run(full=True)
    assert first["text"]["upserted"] == 2 and first["validation"]["ok"]

    second = indexer.run()
    assert second["text"]["upserted"] == 0 and second["images"]["upserted"] == 0

    # change doc b, delete doc a, drop the image
    write_jsonl(settings.chunks_file, [chunk("b", 0, "library text updated"), chunk("b", 1, "more library")])
    write_jsonl(settings.image_chunks_file, [])
    third = indexer.run()
    assert third["text"]["changed_documents"] == 1 and third["text"]["removed_documents"] == 1
    assert third["images"]["deleted"] == 1
    assert store.count(settings.qdrant_text_collection) == 2
    assert third["validation"]["ok"]
    assert read_json(manifest_path(settings))["embedder"] == "hashing:64"


def test_retitled_page_is_reembedded(settings, store):
    settings.ensure_dirs()
    write_jsonl(settings.image_chunks_file, [])
    original = chunk("a", 0, "address and phone")
    write_jsonl(settings.chunks_file, [original])
    indexer = Indexer(settings, HashingEmbedder(64), store)
    indexer.run(full=True)
    write_jsonl(settings.chunks_file, [original.model_copy(update={"page_title": "Contact details"})])
    assert indexer.run()["text"]["changed_documents"] == 1  # same text, new title: the embedding changes


def test_embedder_change_forces_full_rebuild(settings, store):
    settings.ensure_dirs()
    write_jsonl(settings.chunks_file, [chunk("a", 0, "hostel text")])
    write_jsonl(settings.image_chunks_file, [])
    Indexer(settings, HashingEmbedder(64), store).run(full=True)
    report = Indexer(settings, HashingEmbedder(128), store).run()
    assert report["mode"] == "full"
    assert store.collection_dim(settings.qdrant_text_collection) == 128


def test_demo_index_validation(pipeline):
    validation = pipeline.report["index"]["validation"]
    assert validation["ok"], validation
    assert validation["text_points"] == pipeline.report["chunks"]


def test_upsert_splits_a_batch_that_keeps_timing_out(store, monkeypatch):
    store.ensure_collection("t", 4)
    real, sizes = store.client.upsert, []

    def slow_link(name, points, wait):  # a batch of more than 2 points never finishes uploading
        sizes.append(len(points))
        if len(points) > 2:
            raise TimeoutError("The write operation timed out")
        return real(name, points=points, wait=wait)

    monkeypatch.setattr(store.client, "upsert", slow_link)
    monkeypatch.setattr("rag.index.qdrant_store.time.sleep", lambda s: None)
    vecs = np.random.default_rng(0).random((8, 4), dtype=np.float32)
    store.upsert("t", [f"c{i}" for i in range(8)], vecs, [{"chunk_id": f"c{i}"} for i in range(8)])
    assert store.count("t") == 8 and max(s for s in sizes if s <= 2) == 2
    assert store.search("t", vecs[5], 1)[0][0] == "c5"


def test_remote_store_uses_small_batches_and_long_timeout(tmp_path):
    from tests.conftest import make_settings

    settings = make_settings(tmp_path / "data")
    settings.qdrant_url, settings.qdrant_timeout, settings.qdrant_upsert_batch = "http://localhost:1", 99, 8
    remote = QdrantStore.from_settings(settings)
    assert remote.upsert_batch == 8
    remote.close()


def test_vectors_missing_from_the_store_are_uploaded(settings, store):
    write_jsonl(settings.chunks_file, [chunk("d1", 0, "hostel rooms"), chunk("d2", 0, "bus routes")])
    embedder = HashingEmbedder(dim=32)
    Indexer(settings, embedder, store).run()
    store.client.delete_collection(settings.qdrant_text_collection)  # e.g. a new Qdrant Cloud cluster
    assert Indexer.build_needed(settings, embedder, store) == "empty index"
    store.ensure_collection(settings.qdrant_text_collection, 32)
    store.upsert(settings.qdrant_text_collection, ["x"], np.ones((1, 32), dtype=np.float32), [{"chunk_id": "x"}])
    assert Indexer.build_needed(settings, embedder, store) == "missing vectors"
    report = Indexer(settings, embedder, store).run()
    assert report["mode"] == "incremental" and store.count(settings.qdrant_text_collection) >= 2
    assert Indexer.build_needed(settings, embedder, store) == ""


def test_check_qdrant_says_what_to_do_next(tmp_path, capsys):
    from rag.cli import cmd_check_qdrant
    from tests.conftest import make_settings

    settings = make_settings(tmp_path / "data")
    assert cmd_check_qdrant(None, settings) == 1
    assert "QDRANT_URL is empty" in capsys.readouterr().out
    settings.qdrant_url, settings.qdrant_api_key = "https://abc.eu-central-1-0.aws.cloud.qdrant.io:6333", ""
    assert cmd_check_qdrant(None, settings) == 1
    assert "Qdrant Cloud needs one" in capsys.readouterr().out
