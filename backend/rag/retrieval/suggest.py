"""Type-ahead question suggestions: "ai&ds fac" -> "Who are the faculty of the Artificial
Intelligence and Data Science department?".

Candidates are common questions, questions about every department, and the website's own
section pages ("Tell me about NSS & Rotaract Club"). Each word typed must start a word of
the suggestion; department short forms are spelled out first, as for searching.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from rag.config import Settings
from rag.retrieval.corpus import Corpus
from rag.retrieval.hybrid import expand_query

COMMON_QUESTIONS = [
    "What is the intake for each B.E. and B.Tech course?",
    "How do I apply for admission?",
    "What is the eligibility for B.E. and B.Tech admission?",
    "What are the tuition fees?",
    "What is the TNEA counselling code of AAACET?",
    "What scholarships are available for students?",
    "Which university is AAACET affiliated to?",
    "Who is the principal of AAACET?",
    "What is the vision and mission of the college?",
    "Does the college have hostel facilities for boys and girls?",
    "What hostel facilities are available?",
    "Is college bus transport available?",
    "What facilities does the central library have?",
    "Show me photos of the campus library",
    "Show photos of the hostel",
    "Tell me about placements and recruiters",
    "Which companies recruited students in placements?",
    "What is the contact phone number and email of the college?",
    "Is AAACET accredited by NAAC?",
    "What sports facilities are available?",
]
DEPARTMENT_QUESTIONS = [
    "Who are the faculty of the {} department?",
    "Tell me about the {} department",
    "What labs does the {} department have?",
    "What is the vision and mission of the {} department?",
]
# Questions to offer after an answer, by what the answer was about (word starts), most related first.
RELATED_QUESTIONS: list[tuple[tuple[str, ...], list[str]]] = [
    (("fee", "tuition", "cost"), ["What scholarships are available for students?", "How do I apply for admission?",
                                  "What is the intake for each B.E. and B.Tech course?"]),
    (("scholarship",), ["What are the tuition fees?", "How do I apply for admission?",
                        "What is the eligibility for B.E. and B.Tech admission?"]),
    (("admission", "apply", "eligib", "counsel", "tnea", "intake", "seat", "course"),
     ["What is the eligibility for B.E. and B.Tech admission?", "What is the TNEA counselling code of AAACET?",
      "What are the tuition fees?", "What is the intake for each B.E. and B.Tech course?",
      "What scholarships are available for students?"]),
    (("hostel", "room", "mess"), ["Show photos of the hostel", "Is college bus transport available?", "What are the tuition fees?"]),
    (("bus", "transport"), ["Does the college have hostel facilities for boys and girls?", "What is the contact phone number and email of the college?"]),
    (("placement", "recruit", "compan", "job", "salary"), ["Which companies recruited students in placements?",
                                                           "Tell me about placements and recruiters"]),
    (("library", "book"), ["Show me photos of the campus library", "What sports facilities are available?"]),
    (("contact", "phone", "email", "address", "location"), ["How do I apply for admission?", "Is college bus transport available?"]),
]
GENERAL_FOLLOW_UPS = [
    "How do I apply for admission?",
    "What are the tuition fees?",
    "What scholarships are available for students?",
    "What hostel facilities are available?",
    "Tell me about placements and recruiters",
    "What is the contact phone number and email of the college?",
]
_WORD_RE = re.compile(r"[a-z0-9]+")
_SKIP = {"a", "an", "the", "of", "and", "is", "are", "in", "for", "to", "at", "me", "about", "what", "who", "which",
         "how", "does", "do", "tell", "there", "any"}
# also ignored when telling whether a follow-up question was already asked
_SAME_QUESTION_SKIP = _SKIP | {"it", "its", "they", "their", "department", "have", "has", "can", "i", "you", "please", "s"}


@dataclass(frozen=True)
class _Candidate:
    text: str
    words: tuple[str, ...]
    priority: int  # common questions first, then department questions, then section pages


def _about(title: str) -> str:
    """ "Tell me about NSS & Rotaract Activities"; "About AAACET" / "About Us" read naturally."""
    if title.lower().startswith("about "):
        rest = title[6:].strip()
        return "Tell me about the college" if rest.lower() in {"us", "college", "the college"} else f"Tell me about {rest}"
    return f"Tell me about {title}"


def _tidy(title: str) -> str:
    """ "PRINCIPAL MESSAGE" -> "Principal Message"; "curriculum feedback" -> "Curriculum feedback"."""
    if title.isupper():
        title = " ".join(w if len(w) <= 4 and w.isalpha() and w in {"NSS", "NBA", "NAAC", "IQAC", "IIC", "EDC", "UBA"} else w.capitalize()
                         for w in title.split())
    return title[:1].upper() + title[1:]


def _words(text: str) -> tuple[str, ...]:
    return tuple(_WORD_RE.findall(text.lower()))


# first words of department names too common in other questions to name the department alone
_GENERIC_FIRST_WORDS = {"science", "computer", "information"}


def department_in(text: str, settings: Settings) -> str:
    """The department a question is about, as the website names it ("CSE faculty" -> "Computer
    Science and Engineering"); the most specific one when several match, "" when none."""
    words = set(_words(expand_query(text, settings.query_expansions)))
    found = [d for d in settings.departments if set(_words(d)) <= words]
    if found:
        return max(found, key=lambda d: len(_words(d)))
    # one distinctive word is enough ("and civil?", "mechanical labs"): the plainest department it starts
    named = [d for d in settings.departments if _words(d)[0] in words and _words(d)[0] not in _GENERIC_FIRST_WORDS]
    return min(named, key=lambda d: len(_words(d)), default="")


class Suggester:
    def __init__(self, settings: Settings, candidates: list[_Candidate]):
        self.settings = settings
        self.candidates = candidates

    @classmethod
    def build(cls, settings: Settings, corpus: Corpus) -> Suggester:
        texts: dict[str, int] = {q: 3 for q in COMMON_QUESTIONS}
        for department in settings.departments:
            for template in DEPARTMENT_QUESTIONS:
                texts.setdefault(template.format(department), 2)
        # Section pages ("NSS & Rotaract Club"): page titles used by one page only, so generic
        # titles shared by every department ("Faculty List", "About Department") are left out.
        pages = {(c.url, c.page_title.strip()) for c in corpus.chunks.values() if c.metadata.get("kind", "page") in ("page", "section")}
        uses = Counter(title for _, title in pages)
        for title, n in uses.items():
            if n == 1 and 3 <= len(title) <= 60 and not re.search(r"\d{4}|\bpage \d+$", title, re.I) \
                    and "header and footer" not in title:
                texts.setdefault(_about(_tidy(title)), 1)
        return cls(settings, [_Candidate(t, _words(t), p) for t, p in texts.items()])

    def follow_ups(self, question: str, asked: list[str] | None = None, limit: int = 3) -> list[str]:
        """Full questions to offer after an answer: about the same department, then related topics,
        then general admission questions; never one already asked."""
        def gist(text: str) -> frozenset[str]:
            return frozenset(w for w in _words(expand_query(text, self.settings.query_expansions)) if w not in _SAME_QUESTION_SKIP)

        seen = {gist(q) for q in [*(asked or []), question]}
        department = department_in(question, self.settings)
        pool = [t.format(department) for t in DEPARTMENT_QUESTIONS] if department else []
        words = _words(expand_query(question, self.settings.query_expansions))
        for starts, related in RELATED_QUESTIONS:
            if any(w.startswith(s) for w in words for s in starts):
                pool += related
        pool += GENERAL_FOLLOW_UPS
        out: list[str] = []
        for q in pool:
            if gist(q) not in seen and q not in out:
                out.append(q)
        return out[:limit]

    def suggest(self, typed: str, limit: int = 6) -> list[str]:
        typed_words = _words(expand_query(typed, self.settings.query_expansions))
        if not typed_words or len(typed.strip()) < 2:
            return []
        *complete, last = typed_words
        wanted = [w for w in complete if w not in _SKIP]
        ranked = []
        for c in self.candidates:
            if not all(any(cw.startswith(w) for cw in c.words) for w in wanted):
                continue
            if last not in _SKIP or not wanted:  # the word being typed must start a word of the suggestion
                if not any(cw.startswith(last) for cw in c.words):
                    continue
            starts = " ".join(c.words).startswith(" ".join(typed_words))
            ranked.append((-int(starts), -c.priority, len(c.text), c.text))
        ranked.sort()
        return [text for *_, text in ranked[:limit]]
