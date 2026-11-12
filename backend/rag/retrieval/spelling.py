"""Questions typed the way people chat: misspelled words matched to the website's own words.

"hostal fess" searches "hostel fees", "documnets for admision" searches "documents for admission".
The vocabulary is every word the website uses, so a correction is always a word the search can
find. Words the website never uses (chat words, Tanglish, typos too far from any word) are
reported, so the question can be rewritten by the AI model before searching.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

_WORD_RE = re.compile(r"[A-Za-z]+")
# Words of a question that say nothing about its topic: never "corrected", never a reason to rewrite.
COMMON_WORDS = set("""
a an the is are was were be been am do does did can could will would should shall may might must have has had
what which who whom whose when where why how there here this that these those it its i me my mine we our us you your
they their them he she his her of to in on at by for from with about as and or not no yes if than then so any all
some each every many much more most please tell show give list find get got know want need needed help ok okay
hi hello hey thanks thank sir madam mam dear also only just like same other else very well really
what's whats don't dont can't cant isn't im i'm pls plz bro u ur r
""".split())


class Speller:
    def __init__(self, texts: Iterable[str], min_count: int = 1):
        counts = Counter(w.lower() for text in texts for w in _WORD_RE.findall(text) if len(w) >= 3)
        self.vocabulary = {w for w, n in counts.items() if n >= min_count}
        self.counts = counts
        self._by_letter: dict[str, list[str]] = {}
        for word in sorted(self.vocabulary, key=lambda w: -counts[w]):  # frequent words first on ties
            self._by_letter.setdefault(word[0], []).append(word)
        self._cache: dict[str, str | None] = {}

    def _known(self, word: str) -> bool:
        w = word.lower()
        if len(w) < 3 or w in COMMON_WORDS:
            return True
        if w not in self.vocabulary:
            return False
        # a word the website itself misspells now and then ("colege", "hotal") is still a misspelling
        # when a far more common website word is one letter away
        if self.counts[w] < 5 and len(w) >= 4:
            near = self._closest(w, exclude=w)
            return not (near and self.counts[near] >= 20 * self.counts[w])
        return True

    def unknown(self, text: str) -> list[str]:
        """The words of a question the website never uses (typos, chat words, other languages)."""
        return [w for w in _WORD_RE.findall(text) if not self._known(w)]

    def _closest(self, word: str, exclude: str = "") -> str | None:
        """The website word fewest typing slips away: "hostal" -> "hostel" (not "hospital"), "facilty" ->
        "facility" (a dropped letter, not "faculty"); between equally close words the more common one."""
        w = word.lower()
        key = w + "|" + exclude
        if key not in self._cache:
            limit = 1.0 if len(w) <= 5 else 2.0
            best: tuple[float, str] | None = None
            for c in self._by_letter.get(w[0], []):
                if c == exclude or abs(len(c) - len(w)) > 2:
                    continue
                d = typo_distance(w, c, limit)
                if d > limit:
                    continue
                # a common website word beats a rare one (often itself a typo on the site, like "hotal")
                score = d - 0.08 * math.log10(self.counts[c])
                if _is_subsequence(w, c):
                    score -= 0.15  # only letters left out, the most common slip ("facilty" -> "facility")
                if best is None or score < best[0]:
                    best = (score, c)
            self._cache[key] = best[1] if best else None
        return self._cache[key]

    def correct(self, text: str) -> str:
        """The question with each misspelled word (4+ letters) replaced by the closest website word."""
        def fix(m: re.Match) -> str:
            word = m.group(0)
            if len(word) < 4 or self._known(word):
                return word
            return self._closest(word, exclude=word.lower()) or word

        return _WORD_RE.sub(fix, text)


def typo_distance(a: str, b: str, limit: float = 2.0) -> float:
    """Edits between two words, weighted the way people mistype: a swapped pair of letters 0.8, a
    dropped or extra letter 0.9, a wrong letter 1.0. Stops early (returns a large number) past limit."""
    if abs(len(a) - len(b)) * 0.9 > limit:
        return limit + 1
    prev2: list[float] = []
    prev = [j * 0.9 for j in range(len(b) + 1)]
    for i in range(1, len(a) + 1):
        row = [i * 0.9] + [0.0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0.0 if a[i - 1] == b[j - 1] else 1.0
            row[j] = min(prev[j] + 0.9, row[j - 1] + 0.9, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], prev2[j - 2] + 0.8)
        if min(row) > limit:
            return limit + 1
        prev2, prev = prev, row
    return prev[-1]


def _is_subsequence(short: str, long: str) -> bool:
    letters = iter(long)
    return all(ch in letters for ch in short)
