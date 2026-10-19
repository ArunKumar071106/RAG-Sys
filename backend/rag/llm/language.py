"""Is a question written in English? Decides whether it is translated for searching.

The website is in English, so a question in Tamil, Hindi, Arabic, French... is translated
into an English search query (with the hosted LLM) and answered in its own language.
"""

from __future__ import annotations

import re
import unicodedata

# Common English words, plus words people use when asking about a college.
_ENGLISH_WORDS = set("""
a an the is are was were be been am do does did can could will would should shall may might must have has had
what which who whom whose when where why how there here this that these those it its i me my we our you your they their
of to in on at by for from with about as and or not no yes if than then so any all some each every many much more most
please tell show give list find get know want need help available
college campus department dept course courses faculty staff professor principal hod admission admissions fee fees
hostel hostels bus transport library lab labs placement placements contact phone email address intake seats exam
exams result results scholarship scholarships canteen sports club clubs event events name names photo photos
""".split())
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def is_english(text: str) -> bool:
    """True for English questions (and for questions too short to tell, like "AI&DS faculty").

    A question mostly in a non-Latin script (Tamil, Hindi, Arabic, Chinese...) is not English;
    a Latin-script question is English when enough of its words are common English words.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return True
    latin = sum(1 for ch in letters if ord(ch) < 0x250 or "LATIN" in unicodedata.name(ch, ""))
    if latin / len(letters) < 0.5:
        return False
    words = [w.lower() for w in _WORD_RE.findall(text) if len(w) > 1 or w.lower() in {"a", "i"}]
    if len(words) < 3:
        return True
    return sum(1 for w in words if w in _ENGLISH_WORDS) / len(words) >= 0.3
