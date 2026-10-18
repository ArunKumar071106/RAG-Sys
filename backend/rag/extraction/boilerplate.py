"""Corpus-level clean-up: drop blocks repeated across many pages and duplicate pages."""

from __future__ import annotations

from collections import Counter

from rag.models import PageDocument
from rag.utils import sha256_text


def remove_repeated_blocks(docs: list[PageDocument], page_ratio: float = 0.5, min_pages: int = 3) -> list[PageDocument]:
    """Remove text blocks that appear on more than ``page_ratio`` of pages.

    These are typically leftover chrome (address strips, marquee text,
    "Apply now" banners) that survived per-page chrome stripping.
    Headings are kept so heading paths stay intact; tables are kept because
    repeated tables are rare and usually meaningful.
    """
    html_docs = [d for d in docs if d.content_type == "text/html"]
    if len(html_docs) < min_pages:
        return docs
    counts: Counter[str] = Counter()
    for doc in html_docs:
        counts.update({b.text for b in doc.blocks if b.type == "text"})
    threshold = max(min_pages, int(len(html_docs) * page_ratio))
    repeated = {text for text, n in counts.items() if n >= threshold}
    if not repeated:
        return docs
    for doc in html_docs:
        doc.blocks = [b for b in doc.blocks if not (b.type == "text" and b.text in repeated)]
        doc.content_hash = sha256_text("\n".join(b.text for b in doc.blocks))
    return docs


def drop_duplicate_documents(docs: list[PageDocument]) -> tuple[list[PageDocument], dict[str, list[str]]]:
    """Keep one document per identical content hash.

    Returns the unique documents and a mapping ``kept_url -> [duplicate urls]``
    so citations can still mention alternative URLs.
    """
    by_hash: dict[str, PageDocument] = {}
    duplicates: dict[str, list[str]] = {}
    for doc in sorted(docs, key=lambda d: (len(d.url), d.url)):
        has_content = any(b.type != "heading" for b in doc.blocks)
        if not has_content:
            continue
        kept = by_hash.get(doc.content_hash)
        if kept is None:
            by_hash[doc.content_hash] = doc
        else:
            duplicates.setdefault(kept.url, []).append(doc.url)
            kept.images.extend(i for i in doc.images if i.url not in {k.url for k in kept.images})
    return list(by_hash.values()), duplicates
