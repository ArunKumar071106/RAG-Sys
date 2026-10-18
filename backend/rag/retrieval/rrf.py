"""Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, 2009).

score(d) = sum_i  w_i / (k + rank_i(d))      (ranks start at 1)
"""

from __future__ import annotations

from collections.abc import Sequence


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = 60,
                           weights: Sequence[float] | None = None) -> list[tuple[str, float]]:
    if k < 0:
        raise ValueError("k must be non-negative")
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("weights must match rankings")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    order = 0
    for ranking, weight in zip(rankings, weights):
        seen_here: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen_here:  # duplicates within one list count once (best rank)
                continue
            seen_here.add(item)
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
