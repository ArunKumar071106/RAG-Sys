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
