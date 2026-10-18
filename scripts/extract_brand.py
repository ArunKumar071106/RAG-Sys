#!/usr/bin/env python3
"""Measure the official website's branding and write the frontend brand tokens.

    python scripts/extract_brand.py                                  # fetch https://aaaenggcoll.ac.in/
    python scripts/extract_brand.py --url https://aaaenggcoll.ac.in/
    python scripts/extract_brand.py --html saved/index.html --base-url https://aaaenggcoll.ac.in/ \\
                                    --css-dir saved/index_files      # from a page saved in a browser

What it measures (never guesses - anything not found keeps its provisional value
and is listed in the report):
  * colours of the top bar, header, navigation (and hover), footer, links,
    headings and buttons, from the site's CSS rules and inline styles
  * body / heading font families and Google Fonts stylesheet links
  * the header logo (downloaded to frontend/public/brand/), favicon and
    accreditation badges found in the header
  * top-level navigation menu items, top-bar quick links, phone numbers,
    e-mail addresses and the postal address from the footer

Outputs:
  frontend/src/brand/brand.json   (measured: true)
  frontend/src/brand/brand.css    (CSS custom properties)
  frontend/public/brand/*         (logo, favicon, badges)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "frontend" / "src" / "brand"
PUBLIC_BRAND_DIR = ROOT / "frontend" / "public" / "brand"
DEFAULT_URL = "https://aaaenggcoll.ac.in/"
USER_AGENT = "AAACET-RAG-BrandExtractor/1.0"

# ------------------------------------------------------------------ colour helpers
NAMED = {"white": "#ffffff", "black": "#000000", "red": "#ff0000", "blue": "#0000ff", "green": "#008000",
         "navy": "#000080", "maroon": "#800000", "gray": "#808080", "grey": "#808080", "orange": "#ffa500",
         "yellow": "#ffff00", "purple": "#800080", "teal": "#008080", "silver": "#c0c0c0", "gold": "#ffd700"}
COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(" + "|".join(NAMED) + r")\b", re.I)


def to_hex(value: str) -> str | None:
    value = value.strip().lower()
    if value in NAMED:
        return NAMED[value]
    if value.startswith("#"):
        h = value[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        elif len(h) in (6, 8):
            h = h[:6]
        else:
            return None
        return "#" + h
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?", value)
    if m:
        alpha = m.group(4)
        if alpha is not None:
            a = float(alpha.rstrip("%")) / (100 if alpha.endswith("%") else 1)
            if a < 0.5:
                return None  # mostly transparent overlays are not brand colours
        r, g, b = (max(0, min(255, int(float(x)))) for x in m.groups()[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def saturation(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def readable_on(bg: str) -> str:
    return "#ffffff" if contrast(bg, "#ffffff") >= contrast(bg, "#111111") else "#111111"


def darken(hex_color: str, factor: float = 0.8) -> str:
    r, g, b = (int(int(hex_color[i:i + 2], 16) * factor) for i in (1, 3, 5))
    return f"#{r:02x}{g:02x}{b:02x}"


# ------------------------------------------------------------------ CSS parsing
RULE_RE = re.compile(r"([^{}@][^{}]*)\{([^{}]*)\}")
COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)

ROLE_SELECTORS = {
    "topbar": re.compile(r"top-?bar|top-?header|header-?top|top-?nav|topbar|pre-?header|header-top", re.I),
    "header": re.compile(r"(^|[\s.#>])(header|site-header|main-header|masthead|logo-?area|header-?middle|branding)\b", re.I),
    "nav": re.compile(r"(^|[\s.#>])(nav|navbar|navigation|main-?menu|menu-?bar|primary-?menu|mainmenu|menu)\b", re.I),
    "footer": re.compile(r"(^|[\s.#>])(footer|site-footer|footer-?(top|widget|area|bottom|main)|copyright)\b", re.I),
    "button": re.compile(r"\.btn\b|\bbutton\b|\.button\b|read-?more|\.theme-btn|input\[type=.?submit", re.I),
    "heading": re.compile(r"(^|[\s,>])h[1-3]\b|section-?title|heading|\.title\b", re.I),
    "link": re.compile(r"(^|[\s,>])a(:link|:visited)?\s*$", re.I),
}


def parse_css(css: str) -> list[tuple[str, dict[str, str]]]:
    css = COMMENT_RE.sub("", css)
    rules = []
    for selector, body in RULE_RE.findall(css):
        decls = {}
        for decl in body.split(";"):
            if ":" in decl:
                prop, _, val = decl.partition(":")
                decls[prop.strip().lower()] = val.replace("!important", "").strip()
        rules.append((selector.strip(), decls))
    return rules


def collect_colors(rules: list[tuple[str, dict[str, str]]]) -> tuple[dict[str, Counter], dict[str, Counter], Counter]:
    bg: dict[str, Counter] = {role: Counter() for role in ROLE_SELECTORS}
    fg: dict[str, Counter] = {role: Counter() for role in ROLE_SELECTORS}
    hover_bg: Counter = Counter()
    for selector, decls in rules:
        for part in selector.split(","):
            part = part.strip()
            state = re.search(r":hover|:focus|:active|\.active\b|current", part) is not None
            for role, pattern in ROLE_SELECTORS.items():
                if not pattern.search(part):
                    continue
                for prop in ("background-color", "background"):
                    if prop in decls:
                        for m in COLOR_RE.finditer(decls[prop]):
                            if (h := to_hex(m.group(0))):
                                if state:  # hover/active colours are not the element's base colour
                                    if role == "nav":
                                        hover_bg[h] += 1
                                else:
                                    bg[role][h] += 1
                if "color" in decls and not state and (h := to_hex(decls["color"])):
                    fg[role][h] += 1
    return bg, fg, hover_bg


def global_brand_colors(rules) -> Counter:
    counts: Counter = Counter()
    for _, decls in rules:
        for prop, val in decls.items():
            if "color" in prop or prop == "background" or prop.startswith("border"):
                for m in COLOR_RE.finditer(val):
                    h = to_hex(m.group(0))
                    if h and saturation(h) > 0.25 and 0.03 < luminance(h) < 0.8:
                        counts[h] += 1
    return counts


def font_families(rules, role_pattern: re.Pattern | None = None) -> Counter:
    counts: Counter = Counter()
    for selector, decls in rules:
        if role_pattern and not role_pattern.search(selector):
            continue
        family = decls.get("font-family")
        if not family and "font" in decls:
            m = re.search(r"(?:\d+(?:px|em|rem|%)\S*\s+)([\"']?[A-Za-z].*)$", decls["font"])
            family = m.group(1) if m else None
        if family and not family.startswith("var("):
            counts[family.strip()] += 1
    return counts


# ------------------------------------------------------------------ fetching
def fetch(client, url: str) -> tuple[bytes, str]:
    response = client.get(url)
    response.raise_for_status()
    return response.content, response.headers.get("content-type", "")


def same_site(url: str, base: str) -> bool:
    a, b = urlsplit(url).netloc.lower(), urlsplit(base).netloc.lower()
    strip = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return strip(a) == strip(b)


def download_asset(client, url: str, name: str, report: list[str]) -> str | None:
    try:
        data, ctype = fetch(client, url)
    except Exception as exc:
        report.append(f"could not download {url}: {exc}")
        return None
    ext = Path(urlsplit(url).path).suffix.lower() or {"image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg",
                                                      "image/webp": ".webp", "image/x-icon": ".ico"}.get(ctype.split(";")[0], "")
    if ext not in {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".ico"}:
        report.append(f"skipped {url}: unexpected type {ctype}")
        return None
    PUBLIC_BRAND_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_BRAND_DIR / f"{name}{ext}").write_bytes(data)
    return f"/brand/{name}{ext}"


# ------------------------------------------------------------------ HTML analysis
def find_logo(soup, base: str):
    from bs4 import Tag

    candidates = []
    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = img.get("src") or img.get("data-src") or ""
        attrs = " ".join([src, img.get("alt") or "", " ".join(img.get("class") or []), img.get("id") or "",
                          " ".join((img.parent.get("class") or []) if img.parent else [])]).lower()
        score = 0
        if "logo" in attrs:
            score += 5
        if img.find_parent(["header"]) or img.find_parent(class_=re.compile("header|logo|brand", re.I)):
            score += 3
        if img.find_parent("footer"):
            score -= 4
        if re.search(r"naac|nba|aicte|iso|nirf|anna|badge|accredit", attrs):
            score -= 2
        if score > 0 and src:
            candidates.append((score, urljoin(base, src), img.get("alt") or ""))
    candidates.sort(key=lambda c: -c[0])
    return candidates[0] if candidates else None


def find_badges(soup, base: str, logo_url: str | None) -> list[tuple[str, str]]:
    badges = []
    header = soup.find("header") or soup.find(class_=re.compile(r"header", re.I))
    if not header:
        return badges
    for img in header.find_all("img"):
        src = urljoin(base, img.get("src") or "")
        text = f"{src} {img.get('alt') or ''}".lower()
        if src != logo_url and re.search(r"naac|nba|aicte|iso|nirf|accredit|anna|autonomous", text):
            badges.append((src, img.get("alt") or "Accreditation"))
    return badges[:4]


def find_nav(soup, base: str) -> list[dict]:
    navs = soup.find_all("nav") + soup.find_all(class_=re.compile(r"(main|primary)-?menu|navbar|navigation", re.I))
    best: list[dict] = []
    for nav in navs:
        ul = nav.find("ul")
        if not ul:
            continue
        items = []
        for li in ul.find_all("li", recursive=False):
            a = li.find("a")
            if not a:
                continue
            label = " ".join(a.get_text(" ", strip=True).split())
            href = a.get("href") or ""
            if not label or href.startswith(("javascript:", "#")) and not li.find("ul"):
                continue
            item = {"label": label, "href": urljoin(base, href) if href and not href.startswith("#") else base}
            children = []
            sub = li.find("ul")
            if sub:
                for sa in sub.find_all("a")[:15]:
                    sl = " ".join(sa.get_text(" ", strip=True).split())
                    sh = sa.get("href") or ""
                    if sl and sh and not sh.startswith(("#", "javascript:")):
                        children.append({"label": sl, "href": urljoin(base, sh)})
            if children:
                item["children"] = children
            items.append(item)
        if len(items) > len(best):
            best = items
    return best[:10]


PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:\(?0\d{2,4}\)?[\s-]?\d{6,8}|[6-9]\d{4}[\s-]?\d{5})")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PIN_RE = re.compile(r"\b6\d{5}\b")


def find_contact(soup) -> dict:
    regions = [soup.find(class_=re.compile(r"top-?bar|header-?top|top-?header", re.I)), soup.find("footer"),
               soup.find(class_=re.compile(r"footer", re.I))]
    text = "\n".join(r.get_text("\n", strip=True) for r in regions if r is not None)
    phones = list(dict.fromkeys(m.group(0).strip() for m in PHONE_RE.finditer(text)))[:3]
    emails = list(dict.fromkeys(e for e in EMAIL_RE.findall(text) if not e.lower().endswith((".png", ".jpg"))))[:2]
    address: list[str] = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for i, line in enumerate(lines):
        if PIN_RE.search(line):
            start = max(0, i - 3)
            block = [x for x in lines[start:i + 1] if not EMAIL_RE.search(x) and not PHONE_RE.search(x) and len(x) < 90]
            address = block[-4:]
            break
    return {"address": address, "phones": phones, "emails": emails}


def find_utility_links(soup, base: str) -> list[dict]:
    bar = soup.find(class_=re.compile(r"top-?bar|header-?top|top-?header|top-?nav", re.I))
    links = []
    if bar:
        for a in bar.find_all("a", href=True):
            label = " ".join(a.get_text(" ", strip=True).split())
            href = a["href"]
            if label and not href.startswith(("mailto:", "tel:", "#", "javascript:")) and len(label) < 40:
                links.append({"label": label, "href": urljoin(base, href)})
    return links[:6]


# ------------------------------------------------------------------ main
def pick(counter: Counter, default: str | None = None, exclude: set[str] | None = None) -> str | None:
    for color, _ in counter.most_common():
        if exclude and color in exclude:
            continue
        return color
    return default


def build(html: str, base: str, css_texts: list[str], client, google_fonts: list[str]) -> tuple[dict, dict, list[str]]:
    from bs4 import BeautifulSoup

    report: list[str] = []
    soup = BeautifulSoup(html, "lxml")
    inline_css = []
    for tag in soup.find_all(style=True):
        name = " ".join([tag.name, *(tag.get("class") or []), tag.get("id") or ""])
        inline_css.append(f"{name.replace(' ', '.')} {{{tag['style']}}}")
    rules = []
    for text in css_texts + ["\n".join(s.get_text() for s in soup.find_all("style")), "\n".join(inline_css)]:
        rules.extend(parse_css(text))
    report.append(f"parsed {len(rules)} CSS rules from {len(css_texts)} stylesheet(s)")

    bg, fg, hover = collect_colors(rules)
    brand_colors = global_brand_colors(rules)
    white_black = {"#ffffff", "#000000"}
    primary = pick(bg["nav"], exclude=white_black) or pick(bg["header"], exclude=white_black) or pick(brand_colors)
    accent = pick(hover, exclude={primary} | white_black) or pick(bg["button"], exclude={primary} | white_black) \
        or pick(brand_colors, exclude={primary})
    tokens: dict[str, str] = {}
    if primary:
        tokens.update({"--brand-primary": primary, "--brand-primary-dark": darken(primary), "--brand-on-primary": readable_on(primary)})
    if accent:
        tokens.update({"--brand-accent": accent, "--brand-on-accent": readable_on(accent), "--brand-nav-hover-bg": accent})
    for role, bg_var, fg_var in (("topbar", "--brand-topbar-bg", "--brand-topbar-fg"), ("header", "--brand-header-bg", "--brand-header-fg"),
                                 ("nav", "--brand-nav-bg", "--brand-nav-fg"), ("footer", "--brand-footer-bg", "--brand-footer-fg")):
        b = pick(bg[role])
        if b:
            tokens[bg_var] = b
            f = pick(fg[role])
            tokens[fg_var] = f if f and contrast(f, b) >= 3 else readable_on(b)
        else:
            report.append(f"no {role} background colour found - keeping provisional value")
    if (link := pick(fg["link"], exclude={"#ffffff"})):
        tokens["--brand-link"] = link
    if (heading := pick(fg["heading"], exclude={"#ffffff"})):
        tokens["--brand-heading"] = heading
    body_colors = Counter(h for s, d in rules if re.match(r"^\s*(body|html)\b", s) and "color" in d and (h := to_hex(d["color"])))
    if (text_color := pick(body_colors)):
        tokens["--brand-text"] = text_color

    body_fonts = font_families(rules, re.compile(r"^\s*(body|html)\b", re.I)) or font_families(rules)
    heading_fonts = font_families(rules, ROLE_SELECTORS["heading"])
    body_font = pick(body_fonts)
    heading_font = pick(heading_fonts) or body_font
    if body_font:
        tokens["--brand-font-body"] = f"{body_font}, system-ui, sans-serif"
    if heading_font:
        tokens["--brand-font-heading"] = f"{heading_font}, system-ui, sans-serif"

    radius = Counter(d["border-radius"] for s, d in rules if "border-radius" in d and ROLE_SELECTORS["button"].search(s))
    if radius:
        tokens["--brand-radius"] = radius.most_common(1)[0][0].split()[0]

    logo = find_logo(soup, base)
    logo_path = None
    if logo:
        logo_path = download_asset(client, logo[1], "logo", report) if client else None
        report.append(f"logo: {logo[1]}" + ("" if logo_path else " (not downloaded)"))
    else:
        report.append("no logo found - the header keeps the text monogram")
    favicon = soup.find("link", rel=lambda v: v and "icon" in " ".join(v if isinstance(v, list) else [v]).lower())
    if favicon and favicon.get("href") and client:
        download_asset(client, urljoin(base, favicon["href"]), "favicon", report)
    badges = []
    for i, (src, alt) in enumerate(find_badges(soup, base, logo[1] if logo else None)):
        path = download_asset(client, src, f"badge-{i + 1}", report) if client else None
        if path:
            badges.append({"src": path, "alt": alt})

    title = soup.title.get_text(strip=True) if soup.title else ""
    name = (logo[2] if logo and logo[2] and "logo" not in logo[2].lower() else "") or "AAA College of Engineering and Technology"
    nav = find_nav(soup, base)
    if not nav:
        report.append("no navigation menu found - keeping provisional menu")
    brand = {
        "measured": True,
        "note": f"Measured from {base} by scripts/extract_brand.py. Re-run after the website's design changes.",
        "source": base,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "college_name": name,
        "short_name": "AAACET",
        "tagline": "",
        "official_url": base,
        "logo": logo_path,
        "logo_alt": (logo[2] if logo and logo[2] else f"{name} logo"),
        "badges": badges,
        "nav": nav or [{"label": "Home", "href": base}],
        "utility_links": find_utility_links(soup, base) or [{"label": "Official Website", "href": base}],
        "contact": find_contact(soup),
        "fonts": {"body": body_font, "heading": heading_font, "stylesheets": google_fonts},
        "page_title": title,
    }
    return brand, tokens, report


def write_outputs(brand: dict, tokens: dict[str, str]) -> None:
    css_path = BRAND_DIR / "brand.css"
    existing = css_path.read_text(encoding="utf-8")
    current = dict(re.findall(r"(--brand-[\w-]+):\s*([^;]+);", existing))
    current.update(tokens)
    lines = ["/*", f" * Brand design tokens measured from {brand['source']} on {brand['measured_at']}.",
             " * Generated by scripts/extract_brand.py - edit by re-running the script.", " */", ":root {"]
    lines += [f"  {k}: {v};" for k, v in current.items()]
    lines.append("}")
    css_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (BRAND_DIR / "brand.json").write_text(json.dumps(brand, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import httpx

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--html", type=Path, help="use a saved HTML file instead of fetching")
    parser.add_argument("--base-url", help="base URL for resolving links in --html (defaults to --url)")
    parser.add_argument("--css-dir", type=Path, help="folder with the saved page's .css files")
    parser.add_argument("--dry-run", action="store_true", help="print results without writing files")
    args = parser.parse_args(argv)

    base = args.base_url or args.url
    client = httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    if args.html:
        html = args.html.read_text(encoding="utf-8", errors="replace")
    else:
        try:
            data, _ = fetch(client, args.url)
        except Exception as exc:
            print(f"Could not fetch {args.url}: {exc}\nTip: save the page in a browser and use --html/--css-dir.", file=sys.stderr)
            return 2
        html = data.decode("utf-8", errors="replace")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    css_texts: list[str] = []
    google_fonts: list[str] = []
    if args.css_dir:
        css_texts = [p.read_text(encoding="utf-8", errors="replace") for p in sorted(args.css_dir.glob("*.css"))]
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        href = urljoin(base, link["href"])
        if "stylesheet" not in rel:
            continue
        if "fonts.googleapis.com" in href:
            google_fonts.append(href)
        elif not args.css_dir and same_site(href, base):
            try:
                css_texts.append(fetch(client, href)[0].decode("utf-8", errors="replace"))
            except Exception as exc:
                print(f"warning: could not fetch stylesheet {href}: {exc}", file=sys.stderr)

    brand, tokens, report = build(html, base, css_texts, None if args.dry_run else client, google_fonts)
    print("Measured tokens:")
    for key, value in tokens.items():
        print(f"  {key}: {value}")
    print(f"Navigation items: {[i['label'] for i in brand['nav']]}")
    print(f"Contact: {brand['contact']}")
    for line in report:
        print(f"- {line}")
    if not args.dry_run:
        write_outputs(brand, tokens)
        print(f"Wrote {BRAND_DIR / 'brand.json'} and {BRAND_DIR / 'brand.css'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
