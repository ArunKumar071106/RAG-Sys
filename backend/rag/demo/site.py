"""Generate a small FICTIONAL college website for tests and offline demos.

Every fact on these pages is invented ("Demo Institute of Technology") and
exists only to exercise the crawler, extractor, chunker, OCR, retrieval
and UI end to end without network access. None of it describes AAACET.

The site deliberately contains the awkward cases the pipeline must handle:
navigation/footer chrome, a logo repeated on every page, a CSS background
banner, tables with header rows, a poster whose text exists only inside the
image (OCR), an exact duplicate image, a tiny icon, a broken image link, a
duplicate page, a PDF and a robots.txt-disallowed section.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from functools import partial
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLLEGE = "Demo Institute of Technology"
NOTE = "Fictional demo website used for automated tests. Not a real institution."


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                 "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _scene(path: Path, size: tuple[int, int], sky: str, ground: str, shapes: list[tuple[str, tuple[int, int, int, int]]]) -> None:
    img = Image.new("RGB", size, sky)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, int(size[1] * 0.65), size[0], size[1]), fill=ground)
    for color, box in shapes:
        draw.rectangle(box, fill=color)
    img.save(path, quality=90)


def _poster(path: Path) -> None:
    img = Image.new("RGB", (900, 1200), "#fffaf0")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 900, 180), fill="#7a1f1f")
    draw.text((60, 50), "ADMISSIONS OPEN 2026", fill="white", font=_font(64))
    lines = ["B.E. Robotics Engineering", "B.Tech Data Science", "Counselling Code: DIT-0420",
             "Scholarship Test: 14 March", "Helpline: 0000-123456"]
    y = 260
    for line in lines:
        draw.text((60, y), line, fill="#222222", font=_font(52))
        y += 150
    img.save(path)


def _logo(path: Path) -> None:
    img = Image.new("RGB", (240, 240), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((10, 10, 230, 230), outline="#7a1f1f", width=12)
    draw.text((62, 92), "DIT", fill="#7a1f1f", font=_font(64))
    img.save(path)


def _pdf(path: Path, lines: list[str]) -> None:
    """Write a minimal valid single-page PDF with a text layer."""
    content_lines = ["BT", "/F1 14 Tf", "72 720 Td", "18 TL"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"({safe}) Tj T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


NAV = """
<header class="site-header">
  <div class="top-bar">Call: 0000-123456 | Email: info@demo-institute.invalid</div>
  <a href="/"><img src="/assets/logo.png" alt="{college} logo" width="120" height="120"></a>
  <nav class="main-menu"><ul>
    <li><a href="/">Home</a></li><li><a href="/about.html">About</a></li>
    <li><a href="/admissions.html">Admissions</a></li><li><a href="/departments/computer-science.html">Departments</a></li>
    <li><a href="/placements.html">Placements</a></li><li><a href="/facilities.html">Facilities</a></li>
    <li><a href="/contact.html">Contact</a></li><li><a href="/private/staff.html">Staff Login</a></li>
  </ul></nav>
</header>""".replace("{college}", COLLEGE)

FOOTER = f"""
<footer class="site-footer"><p>{COLLEGE}, 1 Example Road, Sample Town 000000.</p>
<p>&copy; 2026 {COLLEGE}. All rights reserved.</p><p class="note">{NOTE}</p></footer>"""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title} | {COLLEGE}</title>
<meta name="description" content="{NOTE}"></head><body>{NAV}
<main id="content">{body}</main>{FOOTER}
<script>console.log('analytics');</script></body></html>"""


LIBRARY_PARAS = [
    "The central library occupies two floors of the academic block and is open from 8:00 AM to 8:00 PM on all working days.",
    "It holds a collection of 42,000 volumes covering engineering, science, mathematics and management, along with 120 print journals.",
    "Students can access digital libraries including IEEE Xplore, Springer Link and the National Digital Library from any campus computer.",
    "A dedicated reading hall seats 250 students and a separate reference section contains handbooks, standards and previous examination papers.",
    "Books may be borrowed for fourteen days; final-year students may borrow up to six books at a time for project work.",
    "The library conducts an orientation session for every first-year batch to explain cataloguing, search tools and borrowing rules.",
    "A book bank scheme lends complete sets of semester textbooks to students from economically weaker sections free of charge.",
    "Overdue books attract a fine of two rupees per day, which is waived during university examination weeks.",
]


def build_demo_site(root: Path) -> Path:
    """Write the fictional site into ``root`` and return it."""
    root.mkdir(parents=True, exist_ok=True)
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    (root / "departments").mkdir(exist_ok=True)
    (root / "private").mkdir(exist_ok=True)
    (root / "notices").mkdir(exist_ok=True)

    _logo(assets / "logo.png")
    _scene(assets / "campus-banner.jpg", (1600, 600), "#9cc9ef", "#5b8c3a",
           [("#d9c7a3", (300, 180, 1300, 420)), ("#7a1f1f", (300, 150, 1300, 190))])
    _scene(assets / "library.jpg", (1000, 700), "#efe6d2", "#8b5a2b",
           [("#5b3a1e", (60, 120, 300, 460)), ("#5b3a1e", (380, 120, 620, 460)), ("#5b3a1e", (700, 120, 940, 460))])
    (assets / "library-reading-hall-copy.jpg").write_bytes((assets / "library.jpg").read_bytes())
    _scene(assets / "computer-lab.jpg", (1000, 700), "#e8eef5", "#9aa5b1",
           [("#1d2b3a", (80 + i * 180, 300, 220 + i * 180, 400)) for i in range(5)])
    _scene(assets / "placement-drive-2025.jpg", (1000, 650), "#f4f1ea", "#c7b299",
           [("#2f4f6f", (100, 200, 900, 260)), ("#444444", (150, 300, 850, 500))])
    _scene(assets / "hostel-block.jpg", (1000, 650), "#bcd9f2", "#6b8e23", [("#c9b38a", (200, 160, 800, 480))])
    _poster(assets / "admission-notice.png")
    Image.new("RGB", (16, 16), "#7a1f1f").save(assets / "icon-arrow.png")

    pages = {
        "index.html": _page("Home", f"""
<section class="hero" style="background-image: url('/assets/campus-banner.jpg')"><h1>Welcome to {COLLEGE}</h1>
<p>{COLLEGE} is a self-financing engineering college offering undergraduate programmes in engineering and technology.</p></section>
<section><h2>Latest News</h2><ul>
<li>Admissions for the 2026 batch are open. See the <a href="/admissions.html">admissions page</a>.</li>
<li>The annual technical symposium "TechVista" will be held on 21 February.</li></ul>
<img src="/assets/admission-notice.png" alt="" width="450" height="600">
<img src="/assets/icon-arrow.png" width="16" height="16" alt="arrow">
</section>"""),
        "about.html": _page("About Us", f"""
<h1>About {COLLEGE}</h1>
<p>{COLLEGE} was established in 2009 by the Example Educational Trust. The college is affiliated to Sample State University and approved by the national technical education council.</p>
<figure><img src="/assets/campus-banner.jpg" alt="Main academic block of the campus"><figcaption>The main academic block, completed in 2012.</figcaption></figure>
<h2>Vision</h2><p>To be a centre of excellence in technical education that produces ethical and skilled engineers.</p>
<h2>Mission</h2><ul><li>Provide outcome-based education with modern laboratories.</li><li>Foster research, innovation and entrepreneurship.</li><li>Serve rural communities through outreach programmes.</li></ul>
<h2>Principal</h2><p>The principal of the college is Dr. A. Example, who has 25 years of teaching experience.</p>"""),
        "admissions.html": _page("Admissions", """
<h1>Admissions 2026</h1>
<p>Admission to first-year B.E. and B.Tech programmes is through the state single-window counselling. The counselling code of the college is DIT-0420.</p>
<h2>Eligibility</h2><p>Candidates must have passed higher secondary examinations with Mathematics, Physics and Chemistry, with a minimum aggregate of 45% (40% for reserved categories).</p>
<h2>Admission Process</h2><ol><li>Register for state counselling online.</li><li>Choose the college code DIT-0420 during choice filling.</li><li>Report to the college with original certificates after allotment.</li></ol>
<h2>Fee Structure</h2>
<table><caption>Tuition fee per year (fictional)</caption><thead><tr><th>Programme</th><th>Intake</th><th>Tuition fee per year</th></tr></thead>
<tbody><tr><td>B.E. Computer Science and Engineering</td><td>120</td><td>Rs. 55,000</td></tr>
<tr><td>B.E. Robotics Engineering</td><td>60</td><td>Rs. 55,000</td></tr>
<tr><td>B.Tech Data Science</td><td>60</td><td>Rs. 60,000</td></tr>
<tr><td>B.E. Civil Engineering</td><td>30</td><td>Rs. 50,000</td></tr></tbody></table>
<h2>Admission Notice</h2>
<img src="/assets/admission-notice.png" alt="" width="450" height="600">
<p>For admission enquiries contact the admission cell on 0000-123456.</p>
<p>Download the <a href="/notices/prospectus.pdf">prospectus (PDF)</a>.</p>"""),
        "departments/computer-science.html": _page("Computer Science and Engineering", """
<h1>Department of Computer Science and Engineering</h1>
<p>The department offers B.E. Computer Science and Engineering with an annual intake of 120 students.</p>
<h2>Head of the Department</h2><p>Dr. B. Sample heads the department and specialises in machine learning.</p>
<h2>Laboratories</h2>
<table><tr><th>Laboratory</th><th>Systems</th></tr><tr><td>Programming Lab</td><td>60</td></tr><tr><td>Networks Lab</td><td>40</td></tr><tr><td>AI and Data Science Lab</td><td>30 GPU workstations</td></tr></table>
<figure><img src="/assets/computer-lab.jpg" alt="Computer laboratory with rows of desktop systems"><figcaption>Programming laboratory</figcaption></figure>"""),
        "placements.html": _page("Placements", """
<h1>Training and Placement Cell</h1>
<p>The placement cell organises aptitude training, mock interviews and campus recruitment drives for final-year students.</p>
<h2>Placement Record 2025</h2>
<table><thead><tr><th>Year</th><th>Students placed</th><th>Highest package</th></tr></thead>
<tbody><tr><td>2025</td><td>212</td><td>Rs. 9.5 LPA</td></tr><tr><td>2024</td><td>188</td><td>Rs. 8.0 LPA</td></tr></tbody></table>
<h2>Recruiters</h2><p>Recruiters who visited in 2025 include Example Software Ltd, Sample Systems and Demo Manufacturing.</p>
<figure><img src="/assets/placement-drive-2025.jpg" alt="Campus recruitment drive in the seminar hall"><figcaption>Campus placement drive, 2025</figcaption></figure>"""),
        "facilities.html": _page("Facilities", f"""
<h1>Campus Facilities</h1>
<h2>Library</h2>{''.join(f'<p>{p}</p>' for p in LIBRARY_PARAS * 3)}
<img src="/assets/library.jpg" alt="Central library reading hall with bookshelves">
<img src="/assets/library-reading-hall-copy.jpg" alt="Library">
<h2>Hostel</h2><p>Separate hostels for boys and girls accommodate 600 students with mess, Wi-Fi and 24-hour security.</p>
<img src="/assets/hostel-block.jpg" alt="Boys hostel block">
<h2>Transport</h2><p>The college operates 18 buses covering towns within 60 km of the campus.</p>
<img src="/assets/missing-photo.jpg" alt="Transport fleet">"""),
        "facilities-copy.html": "",  # filled below (duplicate page)
        "contact.html": _page("Contact Us", f"""
<h1>Contact Us</h1><address>{COLLEGE}<br>1 Example Road<br>Sample Town 000000</address>
<p>Phone: 0000-123456</p><p>Email: info@demo-institute.invalid</p>
<p>Office hours: Monday to Saturday, 9:00 AM to 5:00 PM.</p>"""),
        "private/staff.html": _page("Staff Portal", "<h1>Staff Portal</h1><p>SECRET-ROBOTS-TOKEN must never be crawled.</p>"),
    }
    pages["facilities-copy.html"] = pages["facilities.html"]
    for name, html in pages.items():
        (root / name).write_text(html, encoding="utf-8")
    # the duplicate page is linked from contact so the crawler finds it
    contact = (root / "contact.html").read_text(encoding="utf-8")
    (root / "contact.html").write_text(contact.replace("</main>", '<p><a href="/facilities-copy.html">Facilities (old link)</a></p></main>'), encoding="utf-8")

    _pdf(root / "notices" / "prospectus.pdf", [
        f"{COLLEGE} Prospectus 2026 (fictional)",
        "The college offers four undergraduate programmes.",
        "The anti-ragging committee can be reached at 0000-654321.",
        "The college bus pass costs Rs. 18,000 per year.",
    ])
    (root / "robots.txt").write_text("User-agent: *\nDisallow: /private/\n", encoding="utf-8")
    return root


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_directory(root: Path, port: int = 0) -> tuple[_Server, str]:
    """Serve ``root`` on localhost in a background thread. Returns (server, base_url)."""
    handler = partial(_QuietHandler, directory=str(root))
    server = _Server(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
