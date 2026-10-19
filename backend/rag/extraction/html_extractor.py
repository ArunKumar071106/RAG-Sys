"""Turn raw HTML into an ordered list of structural blocks.

The extractor walks the DOM in document order and emits:
  * heading blocks (maintaining a heading stack -> heading_path),
  * text blocks (paragraphs, list items, loose text inside containers),
  * table blocks (each row rendered as "Header: value | Header: value"),
and collects links and images together with their surrounding context
(alt text, caption, nearest headings, neighbouring text).

Navigation, headers, footers, cookie bars and similar chrome are removed
before walking; repeated cross-page boilerplate is removed later at the
corpus level (see ``boilerplate.py``).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import Comment

from rag.models import Block, ImageRef, Link, PageDocument
from rag.utils import clean_text, is_allowed_host, normalize_url, sha256_text, short_id

REMOVE_TAGS = ("script", "style", "noscript", "iframe", "svg", "form", "button", "select", "input", "template", "canvas", "object", "embed")
CHROME_TAGS = ("nav", "header", "footer", "aside")
CHROME_PATTERN = re.compile(
    r"(^|[-_\s])(nav|navbar|menu|menubar|mega-menu|footer|site-footer|breadcrumbs?|"
    r"sidebar|widget-area|cookie|consent|social|share|skip-link|back-to-top|scroll-?top|pagination|copyright|modal|popup|offcanvas)($|[-_\s])",
    re.I,
)
# "header"/"top-bar" classes are chrome only when they hold no content headings
# (WordPress uses e.g. "entry-header" around the real page title).
WEAK_CHROME_PATTERN = re.compile(r"(^|[-_\s])(header|site-header|top-?bar|topbar)($|[-_\s])", re.I)
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
TEXT_BLOCK_TAGS = {"p", "li", "pre", "blockquote", "dt", "dd", "figcaption", "address", "caption", "summary", "label"}
INLINE_TAGS = {"a", "span", "strong", "b", "em", "i", "u", "small", "sup", "sub", "mark", "abbr", "cite", "code", "font", "time", "q", "s", "big", "bdi", "bdo", "data", "var", "kbd"}
BG_URL_RE = re.compile(r"background(?:-image)?\s*:[^;]*url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)
IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|gif|webp|bmp|tiff?|avif)$", re.I)
DOC_LINK_RE = re.compile(r"\.(pdf)$", re.I)


def _is_chrome(tag: Tag) -> bool:
    if tag.name in ("header", "footer") and tag.find_parent(["article", "section"]) is not None:
        return False  # sectioning header/footer (e.g. post title), not site chrome
    if tag.name in CHROME_TAGS:
        return True
    role = (tag.get("role") or "").lower()
    if role in {"navigation", "banner", "contentinfo", "search", "menu", "menubar"}:
        return True
    tokens = " ".join([tag.get("id") or "", *(tag.get("class") or [])])
    if not tokens:
        return False
    if CHROME_PATTERN.search(tokens):
        return True
    if WEAK_CHROME_PATTERN.search(tokens):
        return tag.find(["h1", "h2", "h3"]) is None or tag.find("nav") is not None
    return False


def _int_attr(value: object) -> int | None:
    if value is None:
        return None
    match = re.match(r"\s*(\d+)", str(value))
    return int(match.group(1)) if match else None


def _best_src(img: Tag) -> str:
    """Lazy-load attribute, else the largest srcset candidate, else src."""
    for attr in ("data-src", "data-lazy-src", "data-original"):
        value = img.get(attr)
        if value and not str(value).startswith("data:"):
            return str(value)
    srcset = img.get("data-srcset") or img.get("srcset")
    if srcset:
        candidates = []
        for part in str(srcset).split(","):
            bits = part.strip().split()
            if not bits:
                continue
            weight = 0
            if len(bits) > 1:
                weight = _int_attr(bits[1].rstrip("wx")) or 0
            candidates.append((weight, bits[0]))
        if candidates:
            return max(candidates)[1]
    src = img.get("src")
    return str(src) if src and not str(src).startswith("data:") else ""


def filename_from_url(url: str) -> str:
    return unquote(PurePosixPath(urlsplit(url).path).name)


def _humanize_filename(name: str) -> str:
    stem = PurePosixPath(name).stem
    stem = re.sub(r"[-_.]+", " ", stem)
    stem = re.sub(r"\b\d{2,4}x\d{2,4}\b", "", stem)  # WordPress size suffixes
    stem = re.sub(r"\b(img|image|dsc|pic|scaled|copy|final|new)\b", "", stem, flags=re.I)
    return re.sub(r"\s+", " ", stem).strip()


def _looks_like_header(first: list[str], rest: list[list[str]]) -> bool:
    """A first table row of short, digit-free labels above rows with the same number of cells
    (e.g. "Department | INTAKE" over "CIVIL ENGINEERING | 60") is a header row."""
    if len(first) < 2 or any(not v or len(v) > 40 or re.search(r"\d", v) for v in first):
        return False
    same_width = [r for r in rest if len(r) == len(first)]
    return len(same_width) >= max(1, len(rest) // 2) and any(re.search(r"\d", v) for r in same_width for v in r)


class _Walker:
    def __init__(self, page_url: str, page_title: str, allowed_domains: list[str]):
        self.page_url = page_url
        self.page_title = page_title
        self.allowed_domains = allowed_domains
        self.blocks: list[Block] = []
        self.links: dict[str, Link] = {}
        self.images: list[ImageRef] = []
        self.heading_stack: list[tuple[int, str]] = []
        self._pending_images: list[ImageRef] = []  # waiting for context_after

    # ---------------------------------------------------------------- helpers
    @property
    def heading_path(self) -> list[str]:
        return [text for _, text in self.heading_stack]

    def _last_text(self) -> str:
        for block in reversed(self.blocks):
            if block.type != "heading":
                return block.text[-300:]
        return ""

    def _emit_text(self, text: str) -> None:
        text = clean_text(text)
        if not text or not re.search(r"[^\W\d_]", text) and len(text) <= 3:
            return  # empty, punctuation or bare counters ("1", "2")
        if not re.search(r"\w", text):
            return
        if self.blocks and self.blocks[-1].type == "text" and self.blocks[-1].text == text:
            return
        self.blocks.append(Block(type="text", text=text, heading_path=self.heading_path))
        self._resolve_pending(text)

    def _resolve_pending(self, text: str) -> None:
        still_pending = []
        for image in self._pending_images:
            if image.caption and text == image.caption:
                still_pending.append(image)  # the figcaption itself is not "following context"
            else:
                image.context_after = text[:300]
        self._pending_images = still_pending

    def _add_link(self, tag: Tag) -> None:
        href = (tag.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            return
        url = normalize_url(href, self.page_url)
        if not url.startswith(("http://", "https://")):
            return
        text = clean_text(tag.get_text(" ", strip=True))
        internal = is_allowed_host(url, self.allowed_domains)
        if url not in self.links:
            self.links[url] = Link(url=url, text=text, internal=internal)

    def _add_image(self, src: str, alt: str = "", title: str = "", caption: str = "", width=None, height=None, background=False) -> None:
        if not src or src.startswith("data:"):
            return
        url = normalize_url(src, self.page_url)
        if not url.startswith(("http://", "https://")):
            return
        filename = filename_from_url(url)
        if filename.lower().endswith((".svg", ".ico")):
            return
        if (width is not None and width < 40) or (height is not None and height < 40):
            return  # spacers, icons, tracking pixels
        ref = ImageRef(
            url=url,
            alt=clean_text(alt),
            title=clean_text(title),
            caption=clean_text(caption),
            filename=filename,
            heading_path=self.heading_path,
            context_before=self._last_text(),
            width_attr=width,
            height_attr=height,
            source_page=self.page_url,
            page_title=self.page_title,
            is_background=background,
        )
        self.images.append(ref)
        self._pending_images.append(ref)

    def _collect_inline(self, node: Tag) -> None:
        for a in node.find_all("a", href=True):
            self._add_link(a)
        for img in node.find_all("img"):
            self._image_from_tag(img)

    def _image_from_tag(self, img: Tag) -> None:
        caption = ""
        figure = img.find_parent("figure")
        if figure is not None:
            cap = figure.find("figcaption")
            if cap is not None:
                caption = cap.get_text(" ", strip=True)
        self._add_image(
            _best_src(img),
            alt=img.get("alt") or "",
            title=img.get("title") or "",
            caption=caption,
            width=_int_attr(img.get("width")),
            height=_int_attr(img.get("height")),
        )

    def _background_image(self, tag: Tag) -> None:
        style = tag.get("style") or ""
        for match in BG_URL_RE.finditer(str(style)):
            src = match.group(1)
            if IMAGE_EXT_RE.search(urlsplit(src).path):
                label = tag.get("aria-label") or tag.get("title") or ""
                self._add_image(src, alt=label, background=True)
        for attr in ("data-bg", "data-background", "data-image"):
            value = tag.get(attr)
            if value and IMAGE_EXT_RE.search(urlsplit(str(value)).path):
                self._add_image(str(value), alt=tag.get("aria-label") or "", background=True)

    # ---------------------------------------------------------------- tables
    def _table(self, table: Tag) -> None:
        rows: list[list[str]] = []
        header: list[str] = []
        for tr in table.find_all("tr"):
            if tr.find_parent("table") is not table:
                continue  # nested table rows are handled with the nested table
            cells = tr.find_all(["th", "td"], recursive=False)
            values = [clean_text(c.get_text(" ", strip=True)) for c in cells]
            if not any(values):
                continue
            is_header = all(c.name == "th" for c in cells) or (tr.find_parent("thead") is not None)
            if is_header and not header and not rows:
                header = values
            else:
                rows.append(values)
        self._collect_inline(table)
        if not header and len(rows) >= 2 and _looks_like_header(rows[0], rows[1:]):
            header, rows = rows[0], rows[1:]  # header row written with <td> cells
        if not rows and header:
            rows, header = [header], []
        if not rows:
            return
        caption_tag = table.find("caption")
        caption = clean_text(caption_tag.get_text(" ", strip=True)) if caption_tag else ""
        rendered: list[str] = []
        for values in rows:
            if header and len(header) == len(values):
                rendered.append(" | ".join(f"{h}: {v}" if h else v for h, v in zip(header, values) if v))
            else:
                rendered.append(" | ".join(v for v in values if v))
        rendered = [r for r in rendered if r]
        header_line = " | ".join(header)
        text_lines = ([caption] if caption else []) + rendered
        self.blocks.append(
            Block(
                type="table",
                text="\n".join(text_lines),
                heading_path=self.heading_path,
                rows=rendered,
                table_header=" | ".join(filter(None, [caption, header_line])),
            )
        )
        self._resolve_pending(rendered[0])

    # ---------------------------------------------------------------- walk
    def _heading(self, tag: Tag) -> None:
        text = clean_text(tag.get_text(" ", strip=True))
        self._collect_inline(tag)
        if not text:
            return
        level = int(tag.name[1])
        while self.heading_stack and self.heading_stack[-1][0] >= level:
            self.heading_stack.pop()
        self.heading_stack.append((level, text))
        self.blocks.append(Block(type="heading", text=text, level=level, heading_path=self.heading_path))

    def walk(self, node: Tag) -> None:
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                self._emit_text(" ".join(buffer))
                buffer.clear()

        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    buffer.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name
            self._background_image(child)
            if name == "br":
                buffer.append("\n")
            elif name == "img":
                flush()
                self._image_from_tag(child)
            elif name in INLINE_TAGS and not child.find(list(HEADING_TAGS | TEXT_BLOCK_TAGS | {"table", "div", "ul", "ol"})):
                if name == "a":
                    self._add_link(child)
                for img in child.find_all("img"):
                    self._image_from_tag(img)
                buffer.append(child.get_text(" ", strip=True))
            elif name in HEADING_TAGS:
                flush()
                self._heading(child)
            elif name == "table":
                flush()
                self._table(child)
            elif name in TEXT_BLOCK_TAGS and not child.find(["table", "ul", "ol", "div", "p"] + list(HEADING_TAGS)):
                flush()
                self._collect_inline(child)
                prefix = "- " if name == "li" else ""
                self._emit_text(prefix + child.get_text(" ", strip=True))
            else:
                flush()
                self.walk(child)
        flush()


def decode_cf_email(encoded: str) -> str:
    """Decode a Cloudflare email-protection hex string (first byte is the XOR key)."""
    try:
        data = bytes.fromhex(encoded)
    except ValueError:
        return ""
    if len(data) < 2:
        return ""
    key = data[0]
    return bytes(b ^ key for b in data[1:]).decode("utf-8", errors="ignore")


def _decode_cf_emails(soup: BeautifulSoup) -> None:
    """Replace Cloudflare-obfuscated addresses ("[email protected]") with the real text."""
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        email = decode_cf_email(str(tag["data-cfemail"]))
        tag.replace_with(email) if email else tag.decompose()
    for a in soup.find_all("a", href=re.compile(r"/cdn-cgi/l/email-protection#")):
        email = decode_cf_email(a["href"].split("#", 1)[1])
        if email:
            a["href"] = f"mailto:{email}"


def _strip_chrome(root: Tag) -> None:
    for tag in root.find_all(REMOVE_TAGS):
        tag.decompose()
    for tag in list(root.find_all(True)):
        if tag.decomposed or tag.parent is None:
            continue
        if tag.name in ("html", "body", "main", "article"):
            continue
        if _is_chrome(tag):
            tag.decompose()
    for tag in root.find_all(attrs={"hidden": True}):
        tag.decompose()
    for tag in root.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        tag.decompose()


def _page_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return clean_text(og["content"])
    if soup.title and soup.title.string:
        return clean_text(soup.title.string)
    h1 = soup.find("h1")
    return clean_text(h1.get_text(" ", strip=True)) if h1 else ""


def extract_html(html: str, url: str, allowed_domains: list[str], fetched_at: str = "") -> PageDocument:
    """Parse one HTML page into a :class:`PageDocument`."""
    soup = BeautifulSoup(html, "lxml")
    _decode_cf_emails(soup)
    title = _page_title(soup)
    kind = page_kind(soup)
    url = normalize_url(url)

    # Links from the whole page (including nav) are useful for crawl metadata,
    # but content blocks only come from the de-chromed main area.
    walker = _Walker(url, title, allowed_domains)
    body = soup.body or soup
    for a in body.find_all("a", href=True):
        walker._add_link(a)

    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
    root = main if main is not None else body
    _strip_chrome(root)
    walker.walk(root)
    # Images left without following context keep context_after empty.

    meta_desc = soup.find("meta", attrs={"name": "description"})
    blocks = walker.blocks
    if meta_desc and meta_desc.get("content") and not any(b.type != "heading" for b in blocks):
        blocks.append(Block(type="text", text=clean_text(meta_desc["content"]), heading_path=[]))

    images = _dedupe_images(walker.images)
    content = "\n".join(b.text for b in blocks)
    return PageDocument(
        doc_id=short_id(url),
        url=url,
        title=title or url,
        blocks=blocks,
        links=list(walker.links.values()),
        images=images,
        content_hash=sha256_text(content),
        content_type="text/html",
        fetched_at=fetched_at,
        kind=kind,
    )


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s-]{8,}\d)")
_PIN_RE = re.compile(r"\b\d{3}\s?\d{3}\b")


def _label_contact_line(text: str) -> str:
    """Footers show contact details next to icons; add the word the icon stands for."""
    bare = text.lstrip("-• ").strip()
    if re.match(r"(?i)(e-?mail|phone|tel|mobile|address|call)\b", bare):
        return text
    if _EMAIL_RE.fullmatch(bare):
        return f"Email: {bare}"
    if _PHONE_RE.fullmatch(bare.replace(",", " ").replace(" ", "")) or re.fullmatch(r"[\d\s,+-]{10,}", bare):
        return f"Phone: {bare}"
    if _PIN_RE.search(bare) and re.search(r"[A-Za-z]{3,}", bare) and len(bare) < 140:
        return f"Address: {bare}"
    return text


def extract_site_chrome(html: str, url: str, allowed_domains: list[str], fetched_at: str = "") -> PageDocument | None:
    """Text from the site-wide header and footer (counselling code, address, phones...).

    These facts are stripped from every page as chrome; capturing them once, from the
    home page, keeps them searchable without repeating them in every chunk. Menus and
    link lists are dropped - only statements are kept.
    """
    soup = BeautifulSoup(html, "lxml")
    _decode_cf_emails(soup)
    regions = []
    for tag in soup.find_all(["header", "footer"]) + soup.find_all(attrs={"role": ["banner", "contentinfo"]}):
        if tag.find_parent(["header", "footer", "main", "article"]) is None and tag not in regions:
            regions.append(tag)
    if not regions:
        return None
    url = normalize_url(url)
    walker = _Walker(url, "Website header and footer", allowed_domains)
    for region in regions:
        for tag in region.find_all(list(REMOVE_TAGS) + ["nav", "img"]):
            tag.decompose()
        for ul in region.find_all(["ul", "ol"]):
            if not ul.decomposed and len(ul.find_all("a")) >= 3:
                ul.decompose()  # menus, quick-link and social lists
        walker.walk(region)
    seen: set[str] = set()
    blocks = []
    for block in walker.blocks:
        # headings such as "COUNSELLING CODE : 4680" carry facts; bare labels ("Contact") don't
        if block.type == "heading" and not re.search(r"\d|:", block.text):
            continue
        if block.text in seen or len(block.text) < 4:
            continue
        if len(block.text) < 25 and not re.search(r"\d|@", block.text):
            continue  # button and link labels ("APPROVALS", "Read More >>")
        if block.type == "heading":
            block = block.model_copy(update={"type": "text", "level": 0})
        seen.add(block.text)
        blocks.append(block.model_copy(update={"heading_path": []}))
    if not blocks:
        return None
    blocks = [b.model_copy(update={"text": _label_contact_line(b.text)}) for b in blocks]
    title = "Official website: header and footer"
    return PageDocument(
        doc_id=short_id(url, "site-chrome"),
        url=url,
        title=title,
        blocks=blocks,
        content_hash=sha256_text("\n".join(b.text for b in blocks)),
        content_type="text/html",
        fetched_at=fetched_at,
    )


def page_kind(soup: BeautifulSoup) -> str:
    """Page type from the CMS body classes (WordPress: "single-post", "page", "single-<type>")."""
    classes = set((soup.body.get("class") if soup.body else None) or [])
    if "single-post" in classes or "post-template-default" in classes:
        return "news"
    if any(c.startswith("single-") for c in classes):
        return "section"  # custom post types such as department or lab pages
    return "page"


def _dedupe_images(images: list[ImageRef]) -> list[ImageRef]:
    seen: dict[str, ImageRef] = {}
    for image in images:
        existing = seen.get(image.url)
        if existing is None:
            seen[image.url] = image
            continue
        # keep the richest metadata
        for field in ("alt", "title", "caption", "context_before", "context_after"):
            if not getattr(existing, field) and getattr(image, field):
                setattr(existing, field, getattr(image, field))
    return list(seen.values())


def extract_pdf_text(text: str, url: str, title: str, fetched_at: str = "") -> PageDocument:
    """Wrap text extracted from a PDF as a document (paragraph blocks)."""
    url = normalize_url(url)
    title = title or _humanize_filename(filename_from_url(url)) or url
    blocks: list[Block] = [Block(type="heading", text=title, level=1, heading_path=[title])]
    for para in re.split(r"\n\s*\n", clean_text(text)):
        para = para.strip()
        if para and re.search(r"\w", para):
            blocks.append(Block(type="text", text=para, heading_path=[title]))
    content = "\n".join(b.text for b in blocks)
    return PageDocument(
        doc_id=short_id(url),
        url=url,
        title=title,
        blocks=blocks,
        content_hash=sha256_text(content),
        content_type="application/pdf",
        fetched_at=fetched_at,
        kind="document",
    )


humanize_filename = _humanize_filename
