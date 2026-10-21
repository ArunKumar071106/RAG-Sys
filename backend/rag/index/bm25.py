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


# Bump when tokenize() changes: stored BM25 indexes hold tokens and are rebuilt on mismatch.
TOKENIZER_VERSION = 2


def _word(raw: str, tokens: list[str]) -> None:
    if raw not in STOPWORDS:
        tokens.append(_stem(raw))


_HONORIFICS = {"dr", "mr", "mrs", "ms", "miss", "prof", "er", "thiru", "tmt", "selvi", "smt", "shri", "sri"}


def _dotted(raw: str, tokens: list[str]) -> None:
    """Abbreviations are content words, never stopwords: "b.e" -> "be", "ph.d" -> "phd", "b.tech" -> "btech".

    Only initials plus one short final part form the abbreviation, so "b.e.courses"
    (a heading written without a space) is "be" + "course", and "aaacet.ac.in"
    is the words "aaacet", "ac", "in" rather than one opaque token.
    """
    parts = raw.split(".")
    if parts[0] in _HONORIFICS:  # "dr.m.sekar" is a name: "dr", "m", "sekar"
        for part in parts:
            _word(part, tokens)
        return
    n = 0
    while n < len(parts) - 1 and len(parts[n]) <= 2:
        n += 1
    if n < len(parts) and len(parts[n]) <= 5 and (n > 0 or len(parts) > 1 and len(parts[1]) <= 2):
        n += 1
    if n >= 2:
        tokens.append("".join(parts[:n]))
    else:
        n = 0
    for part in parts[n:]:
        _word(part, tokens)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if "." in raw:
            _dotted(raw, tokens)
        else:
            _word(raw, tokens)
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

    def weighted_overlap(self, query: str, text: str) -> float:
        """IDF-weighted share of the query's terms that occur in ``text`` (e.g. a page title)."""
        terms = set(tokenize(query))
        if not terms or self._bm25 is None:
            return 0.0
        max_idf = max(self._bm25.idf.values(), default=1.0)
        words = set(tokenize(text))
        weight = {t: max(self._bm25.idf.get(t, max_idf), 0.05) for t in terms}
        return sum(w for t, w in weight.items() if t in words) / sum(weight.values())

    def rare_terms(self, query: str, n: int = 2) -> list[str]:
        """The query's ``n`` rarest terms that occur in the corpus (highest IDF), most rare first;
        none when the query has no more than ``n`` such terms (then they are the whole query)."""
        if self._bm25 is None:
            return []
        known = sorted({t for t in tokenize(query) if t in self._bm25.idf}, key=lambda t: -self._bm25.idf[t])
        return known[:n] if len(known) > n else []

    def coverage(self, query: str, doc_id: str) -> float:
        """Share of the query's IDF weight whose terms occur in the document (0..1).

        Rare, meaningful terms ("hostel", "moon") weigh more than common ones ("college");
        terms that occur nowhere in the corpus get the maximum weight.
        """
        terms = set(tokenize(query))
        if not terms or self._bm25 is None:
            return 0.0
        if not hasattr(self, "_sets"):
            self._sets = {i: set(t) for i, t in zip(self.ids, self.tokens)}
            self._max_idf = max(self._bm25.idf.values(), default=1.0)
        doc = self._sets.get(doc_id, set())
        weight = {t: max(self._bm25.idf.get(t, self._max_idf), 0.05) for t in terms}
        return sum(w for t, w in weight.items() if t in doc) / sum(weight.values())

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
        tmp.write_text(json.dumps({"version": 1, "tokenizer": TOKENIZER_VERSION, "ids": self.ids, "tokens": self.tokens}),
                       encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        if not path.exists():
            return cls([], [])
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(list(data["ids"]), [list(t) for t in data["tokens"]])

    @staticmethod
    def is_current(path: Path) -> bool:
        """True when the stored index exists and was tokenized by this version of tokenize()."""
        if not path.exists():
            return False
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("tokenizer") == TOKENIZER_VERSION
        except (OSError, ValueError):
            return False
