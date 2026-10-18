"""Embedding providers.

``bge-m3``  - BAAI/bge-m3 dense embeddings (1024-d) via sentence-transformers.
              The production default. Requires ``requirements-ml.txt`` and
              access to the model weights (Hugging Face or a local path).
``hashing`` - deterministic feature-hashing embedder with no model download.
              Captures lexical overlap only (words, bigrams, character
              trigrams); it is NOT a semantic model. Used for tests, CI and
              fully offline demos.

The provider name and dimension are stored in the index manifest and the
Qdrant collection; the indexer refuses to mix vectors from different models.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class MissingMLExtras(RuntimeError):
    """sentence-transformers/torch are not installed."""


class BgeM3Embedder:
    """Dense BGE-M3 embeddings; vectors are L2-normalised for cosine search."""

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu", batch_size: int = 16, model=None):
        if model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
            except ImportError as exc:  # pragma: no cover - depends on optional deps
                raise MissingMLExtras(
                    "EMBEDDING_PROVIDER=bge-m3 needs the ML extras: pip install -r backend/requirements-ml.txt"
                ) from exc
            model = SentenceTransformer(model_name, device=device)
        self.model = model
        self.batch_size = batch_size
        self.name = f"bge-m3:{model_name}"
        dim = getattr(model, "get_sentence_embedding_dimension", lambda: None)()
        self.dim = int(dim or 1024)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        # BGE-M3 does not need a query instruction prefix.
        return self.embed_documents([text])[0]


_WORD_RE = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    """Signed feature hashing of unigrams, bigrams and char trigrams (sublinear tf, L2 norm)."""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.name = f"hashing:{dim}"

    def _index(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        return value % self.dim, 1.0 if (value >> 63) & 1 else -1.0

    def _features(self, text: str) -> dict[str, float]:
        words = _WORD_RE.findall(text.lower())
        feats: dict[str, float] = {}
        for w in words:
            feats["w:" + w] = feats.get("w:" + w, 0) + 1.0
            if len(w) > 3:
                padded = f"#{w}#"
                for i in range(len(padded) - 2):
                    key = "c:" + padded[i:i + 3]
                    feats[key] = feats.get(key, 0) + 0.25
        for a, b in zip(words, words[1:]):
            key = f"b:{a}_{b}"
            feats[key] = feats.get(key, 0) + 1.0
        return feats

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for feature, tf in self._features(text).items():
            idx, sign = self._index(feature)
            vec[idx] += sign * (1.0 + math.log(tf)) if tf >= 1 else sign * tf
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._embed(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)


def get_embedder(settings) -> Embedder:
    if settings.embedding_provider == "hashing":
        return HashingEmbedder(settings.hashing_dim)
    try:
        return BgeM3Embedder(settings.embedding_model, settings.embedding_device, settings.embedding_batch_size)
    except MissingMLExtras:
        # Keep the app usable out of the box; a wrong model path etc. still fails loudly.
        log.warning("EMBEDDING_PROVIDER=bge-m3 but sentence-transformers is not installed; using the offline hashing "
                    "embedder. Install backend/requirements-ml.txt for BGE-M3 semantic search (the index rebuilds automatically).")
        return HashingEmbedder(settings.hashing_dim)
