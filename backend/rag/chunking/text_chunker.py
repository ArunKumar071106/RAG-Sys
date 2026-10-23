"""Structure-Aware Recursive Chunking.

1. Group a page's blocks into sections by heading path (page title -> H1 ->
   H2 -> ...).
2. Keep every section its own chunk (one topic per chunk). Only a short
   subsection joins its parent, and one-line sections join each other,
   while they fit in ``chunk_size`` tokens. Tab panels and accordions are
   sections of their own, titled with their tab's name.
3. Split a section that is too large recursively: paragraphs/tables ->
   sentences -> words. Tables are split on row boundaries and every piece
   repeats the table header, so a row is never cut in half.
4. Consecutive pieces of a split section overlap by ``overlap`` tokens
   (whole sentences, taken from the end of the previous piece).

Every chunk records the page title, heading hierarchy, source URL, document
ID and a content hash.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.chunking.tokens import count_tokens
from rag.models import Block, PageDocument, TextChunk
from rag.utils import sha256_text, short_id

_ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "no", "st", "sr", "jr", "vs", "etc", "e.g", "i.e", "fig", "dept",
    "b.e", "m.e", "b.tech", "m.tech", "ph.d", "m.b.a", "m.c.a", "b.sc", "m.sc", "a.m", "p.m", "approx", "est", "govt", "ltd", "pvt",
    "rs", "nos", "vol", "ref", "tel", "ph", "mob", "inc", "co", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
_SENTENCE_END_RE = re.compile(r"([.!?])(\s+)(?=[\"'“(\[]?[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, respecting line breaks and common abbreviations."""
    sentences: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        start = 0
        for match in _SENTENCE_END_RE.finditer(line):
            end = match.end(1)
            prev_word = re.findall(r"([\w.]+)$", line[start:end - 1])
            word = prev_word[0].lower().rstrip(".") if prev_word else ""
            if match.group(1) == "." and (word in _ABBREVIATIONS or len(word) == 1):
                continue
            sentences.append(line[start:end].strip())
            start = match.end()
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


@dataclass
class _Unit:
    kind: str  # "text" | "table"
    text: str
    rows: list[str] = field(default_factory=list)
    header: str = ""

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)


@dataclass
class _Section:
    heading_path: list[str]
    level: int
    units: list[_Unit] = field(default_factory=list)

    @property
    def heading_line(self) -> str:
        if not self.heading_path:
            return ""
        return "#" * min(max(self.level, 1) + 1, 6) + " " + self.heading_path[-1]

    def render(self) -> str:
        parts = [self.heading_line] if self.heading_line else []
        parts.extend(u.text for u in self.units)
        return "\n\n".join(parts)

    @property
    def tokens(self) -> int:
        return count_tokens(self.render())


def _sections(blocks: list[Block]) -> list[_Section]:
    sections: list[_Section] = []
    current = _Section(heading_path=[], level=0)
    for block in blocks:
        if block.type == "heading":
            # a heading with no body of its own still appears in the
            # heading_path of its subsections, so empty sections are dropped
            sections.append(current)
            current = _Section(heading_path=list(block.heading_path), level=block.level)
        elif block.type == "table":
            current.units.append(_Unit("table", block.text, rows=list(block.rows), header=block.table_header))
        else:
            current.units.append(_Unit("text", block.text))
    sections.append(current)
    _fold_heading_lists(sections)
    return [s for s in sections if s.units]


def _fold_heading_lists(sections: list[_Section], min_run: int = 3) -> None:
    """A run of sibling headings with nothing under them is a list drawn as cards (a
    department's labs, each card a title and a link): it becomes a bullet list of its
    parent section instead of being dropped as empty."""
    def parent_of(index: int) -> bool:  # the heading has subsections, so it is not empty
        nxt = sections[index + 1] if index + 1 < len(sections) else None
        path = sections[index].heading_path
        return nxt is not None and len(nxt.heading_path) > len(path) and nxt.heading_path[:len(path)] == path

    i = 0
    while i < len(sections):
        s = sections[i]
        if s.units or not s.heading_path or parent_of(i):
            i += 1
            continue
        run = [i]
        while run[-1] + 1 < len(sections):
            nxt = sections[run[-1] + 1]
            if nxt.units or nxt.heading_path[:-1] != s.heading_path[:-1] or parent_of(run[-1] + 1):
                break
            run.append(run[-1] + 1)
        if len(run) >= min_run:
            parent = next((p for p in reversed(sections[:i]) if p.heading_path == s.heading_path[:-1]), None)
            if parent is None:
                parent = _Section(heading_path=s.heading_path[:-1], level=max(s.level - 1, 0))
                sections.insert(i, parent)
                run = [r + 1 for r in run]
            parent.units.append(_Unit("text", "\n".join(f"- {sections[r].heading_path[-1]}" for r in run)))
        i = run[-1] + 1


def _common_prefix(paths: list[list[str]]) -> list[str]:
    if not paths:
        return []
    prefix = list(paths[0])
    for path in paths[1:]:
        i = 0
        while i < min(len(prefix), len(path)) and prefix[i] == path[i]:
            i += 1
        prefix = prefix[:i]
    return prefix


class StructureAwareChunker:
    def __init__(self, chunk_size: int = 650, overlap: int = 100, min_tokens: int = 40, small_section_tokens: int = 80):
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_tokens = min_tokens
        # a section shorter than this may share a chunk with its neighbour; longer ones stand alone, so a
        # chunk is about one topic ("TNEA B.E./B.Tech. Eligibility", not every admission tab at once)
        self.small_section_tokens = small_section_tokens

    # ------------------------------------------------------------ public API
    def chunk_document(self, doc: PageDocument, duplicate_urls: list[str] | None = None) -> list[TextChunk]:
        pieces: list[tuple[list[str], str]] = []  # (heading_path, text)
        for group in self._merge_small_sections(_sections(doc.blocks), doc.title):
            if len(group) == 1 and group[0].tokens > self.chunk_size:
                section = group[0]
                for text in self._split_section(section):
                    pieces.append((section.heading_path, text))
            else:
                path = _common_prefix([s.heading_path for s in group]) if len(group) > 1 else group[0].heading_path
                pieces.append((path, "\n\n".join(s.render() for s in group)))

        chunks: list[TextChunk] = []
        for index, (path, text) in enumerate(p for p in pieces if count_tokens(p[1]) >= 3):
            content_hash = sha256_text(text)
            chunks.append(
                TextChunk(
                    chunk_id=short_id(doc.doc_id, str(index), content_hash),
                    doc_id=doc.doc_id,
                    url=doc.url,
                    page_title=doc.title,
                    heading_path=[h for h in path if h != doc.title] if path[:1] == [doc.title] else path,
                    text=text,
                    token_count=count_tokens(text),
                    chunk_index=index,
                    content_hash=content_hash,
                    duplicate_urls=duplicate_urls or [],
                    metadata={"content_type": doc.content_type, "fetched_at": doc.fetched_at, "kind": doc.kind},
                )
            )
        return chunks

    # ------------------------------------------------------------ merging
    def _merge_small_sections(self, sections: list[_Section], page_title: str = "") -> list[list[_Section]]:
        """Group sections into chunks. A section joins the chunk before it only when it fits and is a
        short subsection of that chunk's section, or a tiny sibling (same parent). Separate topics, such
        as the tabs of one page, stay apart."""
        groups: list[list[_Section]] = []
        current: list[_Section] = []
        current_tokens = 0
        for section in sections:
            tokens = section.tokens
            if current and current_tokens + tokens <= self.chunk_size:
                first, last = current[0].heading_path, current[-1].heading_path
                path = section.heading_path
                # a short subsection stays with its section (not with the page banner heading, which
                # every section is under), and a tiny sibling (a heading with a line under it) joins
                own = first[1:] if first[:1] == [page_title] else first  # the page banner heading is not a section
                subsection = bool(own) and len(path) > len(first) and path[:len(first)] == first
                small = tokens < self.small_section_tokens or current_tokens < self.small_section_tokens
                siblings = len(path) == len(last) and path[:-1] == last[:-1]
                # one-line sections share a chunk with each other, never with a full section (whose
                # name the chunk would lose for the common parent's)
                tiny_text = tokens < self.min_tokens and all(s.tokens < self.min_tokens for s in current) \
                    and not any(u.kind == "table" for s in (section, current[-1]) for u in s.units)
                if subsection and small or siblings and tiny_text:
                    current.append(section)
                    current_tokens += tokens
                    continue
            if current:
                groups.append(current)
            current, current_tokens = [section], tokens
        if current:
            groups.append(current)
        return groups

    # ------------------------------------------------------------ splitting
    def _split_section(self, section: _Section) -> list[str]:
        heading = section.heading_line
        budget = self.chunk_size - (count_tokens(heading) if heading else 0)
        atoms: list[tuple[str, str]] = []  # (kind, text) where kind in {"text","row","sentence"}
        for unit in section.units:
            if unit.kind == "table":
                atoms.extend(self._table_atoms(unit, budget))
            elif unit.tokens <= budget:
                atoms.append(("text", unit.text))
            else:
                atoms.extend(("sentence", s) for s in self._sentence_atoms(unit.text, budget))

        pieces: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for kind, text in atoms:
            tokens = count_tokens(text)
            if current and current_tokens + tokens > budget:
                pieces.append("\n\n".join(current))
                tail = self._overlap_tail(current, kind)
                current = [tail] if tail else []
                current_tokens = count_tokens(tail) if tail else 0
            current.append(text)
            current_tokens += tokens
        if current:
            pieces.append("\n\n".join(current))

        # fold a tiny trailing piece back into its predecessor when it fits
        if len(pieces) > 1 and count_tokens(pieces[-1]) < self.min_tokens and \
                count_tokens(pieces[-2]) + count_tokens(pieces[-1]) <= self.chunk_size + self.overlap:
            tail = pieces.pop()
            pieces[-1] = pieces[-1] + "\n\n" + tail
        return [f"{heading}\n\n{p}" if heading else p for p in pieces]

    def _overlap_tail(self, current: list[str], next_kind: str) -> str:
        """Last whole sentences of the previous piece, up to ``overlap`` tokens."""
        if self.overlap <= 0 or next_kind == "row":
            return ""
        sentences = split_sentences("\n".join(current))
        tail: list[str] = []
        tokens = 0
        for sentence in reversed(sentences):
            n = count_tokens(sentence)
            if tokens + n > self.overlap:
                break
            tail.insert(0, sentence)
            tokens += n
        return " ".join(tail)

    def _table_atoms(self, unit: _Unit, budget: int) -> list[tuple[str, str]]:
        if unit.tokens <= budget:
            return [("text", unit.text)]
        header = unit.header
        header_tokens = count_tokens(header) if header else 0
        atoms: list[tuple[str, str]] = []
        group: list[str] = []
        group_tokens = header_tokens
        for row in unit.rows:
            row_tokens = count_tokens(row)
            if group and group_tokens + row_tokens > budget:
                atoms.append(("row", "\n".join(([header] if header else []) + group)))
                group, group_tokens = [], header_tokens
            if row_tokens > budget - header_tokens:
                atoms.extend(("row", s) for s in self._sentence_atoms(row, budget))
                continue
            group.append(row)
            group_tokens += row_tokens
        if group:
            atoms.append(("row", "\n".join(([header] if header else []) + group)))
        return atoms

    def _sentence_atoms(self, text: str, budget: int) -> list[str]:
        atoms: list[str] = []
        for sentence in split_sentences(text):
            if count_tokens(sentence) <= budget:
                atoms.append(sentence)
                continue
            words = sentence.split()
            piece: list[str] = []
            for word in words:
                piece.append(word)
                if count_tokens(" ".join(piece)) >= budget:
                    atoms.append(" ".join(piece[:-1]))
                    piece = [word]
            if piece:
                atoms.append(" ".join(piece))
        return [a for a in atoms if a]
