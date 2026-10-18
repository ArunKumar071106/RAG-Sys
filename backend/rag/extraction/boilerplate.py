"""Corpus-level clean-up: drop blocks repeated across many pages and duplicate pages."""

from __future__ import annotations

from collections import defaultdict

from rag.models import PageDocument
from rag.utils import sha256_text


def remove_repeated_blocks(docs: list[PageDocument], page_ratio: float = 0.5, min_pages: int = 3,
                           keep_once_min: int = 5) -> list[PageDocument]:
    """Clean up text blocks repeated across pages.

    * On more than ``page_ratio`` of all pages: site chrome that survived
      per-page stripping ("Content is protected", marquee text) - removed everywhere.
    * On ``keep_once_min`` or more pages (e.g. a department sidebar or intro shown
      on every page of that department): kept once, on the page with the shortest
      URL (usually the section's main page), and removed from the others.

    Headings are kept so heading paths stay intact; tables are kept because
    repeated tables are rare and usually meaningful.
    """
    html_docs = [d for d in docs if d.content_type == "text/html"]
    if len(html_docs) < min_pages:
        return docs
    pages_with: dict[str, list[PageDocument]] = defaultdict(list)
    for doc in html_docs:
        for text in {b.text for b in doc.blocks if b.type == "text"}:
            pages_with[text].append(doc)
    threshold = max(min_pages, int(len(html_docs) * page_ratio))
    remove_everywhere = {t for t, pages in pages_with.items() if len(pages) >= threshold}
    keep_in: dict[str, str] = {
        t: min(pages, key=lambda d: (len(d.url), d.url)).doc_id
        for t, pages in pages_with.items() if keep_once_min <= len(pages) < threshold
    }
    if not remove_everywhere and not keep_in:
        return docs
    for doc in html_docs:
        kept = []
        for b in doc.blocks:
            if b.type == "text" and (b.text in remove_everywhere or keep_in.get(b.text, doc.doc_id) != doc.doc_id):
                continue
            kept.append(b)
        doc.blocks = kept
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
