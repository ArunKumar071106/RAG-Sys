"""Thin wrapper over Qdrant for text and image collections.

Works with a Qdrant server (``QDRANT_URL``) or embedded local mode
(``QDRANT_PATH``) - the latter needs no extra service and is used for
development and tests. Note that local mode locks its directory to one
process: run the API *or* a CLI indexing command, or use a Qdrant server.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

log = logging.getLogger(__name__)
_NAMESPACE = uuid.UUID("6f1c1d1e-7d3b-4c8a-9f43-0000aa000001")


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


class VectorDimensionMismatch(RuntimeError):
    pass


class QdrantStore:
    def __init__(self, client: QdrantClient, upsert_batch: int = 64, remote: bool = False):
        self.client = client
        self.upsert_batch = upsert_batch
        # a Qdrant server or Qdrant Cloud: every call is a network round trip, so callers may overlap them
        self.remote = remote
        self._known: set[str] = set()  # collections seen to exist, so a search is one round trip

    @classmethod
    def from_settings(cls, settings) -> QdrantStore:
        if settings.qdrant_url:
            client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None,
                                  timeout=settings.qdrant_timeout, check_compatibility=False)
            return cls(client, upsert_batch=max(1, settings.qdrant_upsert_batch), remote=True)
        else:
            settings.qdrant_local_path.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=str(settings.qdrant_local_path))
        return cls(client)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------- collections
    def collection_dim(self, name: str) -> int | None:
        if not self.client.collection_exists(name):
            return None
        info = self.client.get_collection(name)
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            vectors = next(iter(vectors.values()))
        return int(vectors.size)

    def ensure_collection(self, name: str, dim: int, recreate: bool = False) -> None:
        existing = self.collection_dim(name)
        if existing is not None and (recreate or existing != dim):
            if existing != dim and not recreate:
                raise VectorDimensionMismatch(
                    f"Collection {name!r} has {existing}-d vectors but the embedder produces {dim}-d. "
                    "Run a full reindex (python -m rag.cli index --full) to rebuild it."
                )
            self.client.delete_collection(name)
            self._known.discard(name)
            existing = None
        if existing is None:
            self.client.create_collection(name, vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE))
            for field in ("doc_id", "url", "source_page"):
                try:
                    self.client.create_payload_index(name, field, qm.PayloadSchemaType.KEYWORD)
                except Exception:  # local mode ignores payload indexes
                    pass

    def count(self, name: str) -> int:
        if name not in self._known:
            if not self.client.collection_exists(name):
                return 0
            self._known.add(name)
        try:
            return int(self.client.count(name, exact=True).count)
        except Exception:
            self._known.discard(name)
            if not self.client.collection_exists(name):
                return 0
            raise

    # ------------------------------------------------------------- writes
    def upsert(self, name: str, ids: Sequence[str], vectors: np.ndarray, payloads: Sequence[dict],
               batch_size: int | None = None, retries: int = 2) -> None:
        batch_size = batch_size or self.upsert_batch
        # 6 decimals keep cosine scores exact to ~1e-6 and halve the upload's size
        rounded = np.round(np.asarray(vectors, dtype=np.float64), 6)
        for start in range(0, len(ids), batch_size):
            points = [
                qm.PointStruct(id=point_id(cid), vector=vec.tolist(), payload=payload)
                for cid, vec, payload in zip(ids[start:start + batch_size], rounded[start:start + batch_size],
                                             payloads[start:start + batch_size])
            ]
            self._upsert_points(name, points, retries)

    def _upsert_points(self, name: str, points: list, retries: int) -> None:
        """Send one batch; when it keeps failing (a timeout on a slow uplink), send it in halves."""
        for attempt in range(retries + 1):
            try:
                self.client.upsert(name, points=points, wait=True)
                return
            except Exception as exc:
                if attempt == retries:
                    if len(points) == 1:
                        raise
                    log.warning("Qdrant upsert of %d points failed (%s); sending it in halves", len(points), exc)
                    half = len(points) // 2
                    self._upsert_points(name, points[:half], retries)
                    self._upsert_points(name, points[half:], retries)
                    return
                log.warning("Qdrant upsert failed (%s); retrying", exc)
                time.sleep(0.5 * (2 ** attempt))

    def delete_by_field(self, name: str, field: str, values: Sequence[str]) -> None:
        if not values or not self.client.collection_exists(name):
            return
        selector = qm.FilterSelector(filter=qm.Filter(must=[qm.FieldCondition(key=field, match=qm.MatchAny(any=list(values)))]))
        self.client.delete(name, points_selector=selector, wait=True)

    def delete_ids(self, name: str, chunk_ids: Sequence[str]) -> None:
        if not chunk_ids or not self.client.collection_exists(name):
            return
        self.client.delete(name, points_selector=qm.PointIdsList(points=[point_id(c) for c in chunk_ids]), wait=True)

    # ------------------------------------------------------------- reads
    def search(self, name: str, vector: np.ndarray, limit: int) -> list[tuple[str, float, dict]]:
        if name not in self._known:
            if not self.client.collection_exists(name):
                return []
            self._known.add(name)
        try:
            result = self.client.query_points(name, query=vector.tolist(), limit=limit, with_payload=True)
        except Exception:
            self._known.discard(name)
            if not self.client.collection_exists(name):  # deleted since: nothing to find
                return []
            raise
        return [(p.payload.get("chunk_id", ""), float(p.score), p.payload) for p in result.points]

    def existing_ids(self, name: str, chunk_ids: Sequence[str], batch_size: int = 256) -> set[str]:
        """The subset of ``chunk_ids`` already stored in the collection."""
        if not chunk_ids or not self.client.collection_exists(name):
            return set()
        found: set[str] = set()
        for start in range(0, len(chunk_ids), batch_size):
            points = self.client.retrieve(name, ids=[point_id(c) for c in chunk_ids[start:start + batch_size]],
                                          with_payload=["chunk_id"], with_vectors=False)
            found.update(p.payload.get("chunk_id", "") for p in points)
        return found

    def get(self, name: str, chunk_id: str) -> dict | None:
        if not self.client.collection_exists(name):
            return None
        points = self.client.retrieve(name, ids=[point_id(chunk_id)], with_payload=True)
        return points[0].payload if points else None
