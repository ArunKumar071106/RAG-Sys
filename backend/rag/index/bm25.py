"""BM25 keyword index.

Stored as plain JSON (ids + tokens), never pickle, so loading an index file
cannot execute code. The BM25Okapi model is rebuilt on load, which takes
milliseconds for a college-sized corpus.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from", "is", "are", "was", "were",
    "be", "been", "it", "its", "this", "that", "these", "those", "as", "what", "which", "who", "whom", "how", "when",
    "where", "why", "do", "does", "did", "can", "could", "will", "would", "should", "about", "me", "my", "i", "you",
    "your", "we", "our", "they", "their", "there", "any", "all", "tell", "please", "give", "show", "list", "us", "have", "has",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.+#][a-z0-9]+)*")


def _stem(token: str) -> str:
    """Very light plural/gerund folding; enough for keyword matching on a small corpus."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith(("sses", "xes", "zes", "ches", "shes", "uses")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if "." in raw:  # abbreviations like "B.E." / "Ph.D" are content words, never stopwords
            tokens.append(raw.replace(".", ""))
        elif raw not in STOPWORDS:
            tokens.append(_stem(raw))
    return tokens


class BM25Index:
    def __init__(self, ids: list[str], tokens: list[list[str]]):
        self.ids = ids
        self.tokens = tokens
        self._bm25 = BM25Okapi(tokens) if tokens and any(tokens) else None

    @classmethod
    def build(cls, items: list[tuple[str, str]]) -> BM25Index:
        return cls([i for i, _ in items], [tokenize(t) for _, t in items])

    def __len__(self) -> int:
        return len(self.ids)

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        # rank_bm25 can yield tiny negative IDF for terms in >half the docs;
        # only documents that actually contain a query term count as matches.
        qset = set(q)
        order = np.argsort(-scores)
        results = []
        for idx in order[: max(limit * 3, limit)]:
            if not qset.intersection(self.tokens[idx]):
                continue
            results.append((self.ids[idx], float(scores[idx])))
            if len(results) >= limit:
                break
        return results

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "ids": self.ids, "tokens": self.tokens}), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        if not path.exists():
            return cls([], [])
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(list(data["ids"]), [list(t) for t in data["tokens"]])
