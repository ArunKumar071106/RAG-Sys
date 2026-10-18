from rag.extraction.boilerplate import drop_duplicate_documents, remove_repeated_blocks
from rag.extraction.html_extractor import extract_html, extract_pdf_text

BASE = "https://college.example/page"
ALLOWED = ["college.example"]

HTML = """
<html><head><title>Admissions | College</title></head><body>
<header class="site-header"><img src="/logo.png" alt="logo"><nav><a href="/a">Menu A</a></nav></header>
<div class="top-bar">Call us 123</div>
<main>
  <article><header class="entry-header"><h1>Admissions 2026</h1></header>
  <p>Admission is through <a href="/counselling">state counselling</a>.</p>
  <h2>Eligibility</h2>
  <p>Pass in higher secondary with Maths.</p>
  <div>Loose text inside a div <strong>with bold</strong> part.</div>
  <h3>Documents</h3>
  <ul><li>Mark sheet</li><li>Transfer certificate</li></ul>
  <h2>Fees</h2>
  <table><thead><tr><th>Course</th><th>Fee</th></tr></thead>
    <tbody><tr><td>CSE</td><td>50,000</td></tr><tr><td>ECE</td><td>45,000</td></tr></tbody></table>
  <figure><img src="/img/campus.jpg" srcset="/img/campus-300.jpg 300w, /img/campus-1200.jpg 1200w" alt="Campus view">
    <figcaption>Main block</figcaption></figure>
  <p>Text after the figure.</p>
  <img src="/img/icon.png" width="16" height="16">
  <img src="data:image/png;base64,AAAA">
  <section class="banner" style="background-image: url('/img/banner.jpg')"></section>
  <a href="https://external.example/x">External</a>
  <script>var x = 1;</script>
  </article>
</main>
<footer class="site-footer"><p>Copyright College</p></footer>
</body></html>
"""


def test_extract_html_structure_and_chrome_removal():
    doc = extract_html(HTML, BASE, ALLOWED)
    texts = [b.text for b in doc.blocks]
    assert doc.title == "Admissions | College"
    assert "Admissions 2026" in texts  # entry-header inside article is content
    assert not any("Call us" in t or "Copyright" in t or "Menu A" in t or "var x" in t for t in texts)
    assert "Loose text inside a div with bold part." in texts
    assert "- Mark sheet" in texts


def test_heading_path_tracks_hierarchy():
    doc = extract_html(HTML, BASE, ALLOWED)
    by_text = {b.text: b for b in doc.blocks}
    assert by_text["Pass in higher secondary with Maths."].heading_path == ["Admissions 2026", "Eligibility"]
    assert by_text["- Mark sheet"].heading_path == ["Admissions 2026", "Eligibility", "Documents"]


def test_tables_render_rows_with_headers():
    doc = extract_html(HTML, BASE, ALLOWED)
    table = next(b for b in doc.blocks if b.type == "table")
    assert table.rows == ["Course: CSE | Fee: 50,000", "Course: ECE | Fee: 45,000"]
    assert table.table_header == "Course | Fee"
    assert table.heading_path == ["Admissions 2026", "Fees"]


def test_images_with_context_srcset_background_and_filters():
    doc = extract_html(HTML, BASE, ALLOWED)
    urls = {i.url: i for i in doc.images}
    campus = urls["https://college.example/img/campus-1200.jpg"]  # largest srcset candidate
    assert campus.alt == "Campus view"
    assert campus.caption == "Main block"
    assert campus.heading_path == ["Admissions 2026", "Fees"]
    assert campus.context_after.startswith("Text after the figure")
    assert campus.source_page == "https://college.example/page"
    assert "https://college.example/img/banner.jpg" in urls and urls["https://college.example/img/banner.jpg"].is_background
    assert not any("icon.png" in u or u.startswith("data:") or "logo" in u for u in urls)


def test_links_are_absolute_and_flagged_internal():
    doc = extract_html(HTML, BASE, ALLOWED)
    links = {link.url: link for link in doc.links}
    assert links["https://college.example/counselling"].internal
    assert not links["https://external.example/x"].internal


def test_repeated_blocks_removed_across_pages():
    pages = [extract_html(f"<html><body><main><h1>P{i}</h1><p>Unique {i}</p><p>Apply now for 2026!</p></main></body></html>",
                          f"https://college.example/p{i}", ALLOWED) for i in range(4)]
    cleaned = remove_repeated_blocks(pages, page_ratio=0.5)
    for i, doc in enumerate(cleaned):
        texts = [b.text for b in doc.blocks]
        assert "Apply now for 2026!" not in texts
        assert f"Unique {i}" in texts


def test_duplicate_documents_detected():
    html = "<html><body><main><h1>Same</h1><p>Same content</p></main></body></html>"
    a = extract_html(html, "https://college.example/a", ALLOWED)
    b = extract_html(html, "https://college.example/a-copy", ALLOWED)
    unique, dups = drop_duplicate_documents([a, b])
    assert len(unique) == 1
    assert dups == {"https://college.example/a": ["https://college.example/a-copy"]}


def test_pdf_text_becomes_paragraph_blocks():
    doc = extract_pdf_text("Line one.\n\nSecond paragraph here.", "https://college.example/files/fee-notice_2026.pdf", "")
    assert doc.title == "fee notice 2026"
    assert [b.text for b in doc.blocks if b.type == "text"] == ["Line one.", "Second paragraph here."]
    assert doc.content_type == "application/pdf"
