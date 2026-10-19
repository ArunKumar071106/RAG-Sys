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


def test_cloudflare_obfuscated_emails_are_decoded():
    from rag.extraction.html_extractor import decode_cf_email

    # "info@aaa.ac.in" XOR-encoded with key 0x42, as Cloudflare does
    encoded = "42" + "".join(f"{ord(c) ^ 0x42:02x}" for c in "info@aaa.ac.in")
    assert decode_cf_email(encoded) == "info@aaa.ac.in"
    html = (f'<html><body><main><p>Email: <a href="/cdn-cgi/l/email-protection#{encoded}">'
            f'<span class="__cf_email__" data-cfemail="{encoded}">[email&#160;protected]</span></a></p></main></body></html>')
    doc = extract_html(html, BASE, ALLOWED)
    assert [b.text for b in doc.blocks] == ["Email: info@aaa.ac.in"]
    assert decode_cf_email("zz") == "" and decode_cf_email("") == ""


def test_site_chrome_keeps_header_footer_facts_but_not_menus():
    from rag.extraction.html_extractor import extract_site_chrome

    html = """<html><head><title>College</title></head><body>
    <header><h2>COUNSELLING CODE : 4680</h2><nav><ul><li><a href='/a'>Home</a></li></ul></nav>
      <ul><li><a href='/x'>Approvals</a></li><li><a href='/y'>NAAC</a></li><li><a href='/z'>Login</a></li></ul></header>
    <main><p>Page body</p></main>
    <footer><h3>Contact</h3><p>Kamarajar Educational Road, Amathur - 626 005</p><p>04562-251111</p></footer></body></html>"""
    doc = extract_site_chrome(html, "https://college.example/", ALLOWED)
    texts = [b.text for b in doc.blocks if b.type == "text"]
    assert texts == ["COUNSELLING CODE : 4680", "Address: Kamarajar Educational Road, Amathur - 626 005", "Phone: 04562-251111"]
    assert doc.doc_id != extract_html(html, "https://college.example/", ALLOWED).doc_id
    assert "Page body" not in texts and "Home" not in " ".join(texts)


def test_section_repeated_blocks_kept_once_on_landing_page():
    pages = []
    for i in range(10):
        dept = i < 6  # six department pages share a sidebar intro; four other pages don't
        url = "https://college.example/cse/" + ("about-department/" if i == 3 else f"p{i}/") if dept else f"https://college.example/other-{i}/"
        intro = "<p>The CSE department was established in 2013 with modern labs.</p>" if dept else ""
        pages.append(extract_html(f"<html><body><main><h1>P{i}</h1>{intro}<p>Unique {i}</p><p>{i}</p></main></body></html>", url, ALLOWED))
    cleaned = remove_repeated_blocks(pages, page_ratio=0.8, keep_once_min=5)
    holders = [d.url for d in cleaned if any("established in 2013" in b.text for b in d.blocks)]
    assert holders == ["https://college.example/cse/about-department/"]  # not the shorter /cse/p1/
    assert all(any(b.text == f"Unique {i}" for b in d.blocks) for i, d in enumerate(cleaned))
    assert not any(b.text.isdigit() for d in cleaned for b in d.blocks)


def test_header_row_written_with_td_cells_is_detected():
    html = """<html><body><main><h2>B.E. Courses</h2><table>
      <tr><td>Department</td><td>INTAKE</td></tr>
      <tr><td>CIVIL ENGINEERING</td><td>60</td></tr><tr><td>COMPUTER SCIENCE AND ENGINEERING</td><td>180</td></tr>
    </table></main></body></html>"""
    table = next(b for b in extract_html(html, BASE, ALLOWED).blocks if b.type == "table")
    assert table.rows == ["Department: CIVIL ENGINEERING | INTAKE: 60", "Department: COMPUTER SCIENCE AND ENGINEERING | INTAKE: 180"]


def test_long_header_labels_are_still_a_header_row():
    long_label = "Date of Leaving (In case Currently Associated is \u201cNo\u201d)"
    html = f"""<html><body><main><h2>Faculty</h2><table>
      <tr><td><strong>S.No</strong></td><td><strong>Name of the Faculty</strong></td><td><strong>{long_label}</strong></td></tr>
      <tr><td>1.</td><td>Dr.C.Senthil Kumar</td><td></td></tr><tr><td>2.</td><td>Dr.R.Pon Vengatesh</td><td></td></tr>
    </table></main></body></html>"""
    table = next(b for b in extract_html(html, BASE, ALLOWED).blocks if b.type == "table")
    assert table.rows == ["S.No: 1. | Name of the Faculty: Dr.C.Senthil Kumar", "S.No: 2. | Name of the Faculty: Dr.R.Pon Vengatesh"]


def test_numeric_first_row_is_not_a_header():
    html = """<html><body><main><table>
      <tr><td>2024</td><td>Placed 120</td></tr><tr><td>2025</td><td>Placed 140</td></tr><tr><td>2026</td><td>Placed 150</td></tr>
    </table></main></body></html>"""
    table = next(b for b in extract_html(html, BASE, ALLOWED).blocks if b.type == "table")
    assert table.rows[0] == "2024 | Placed 120" and not table.table_header


def test_link_card_menu_is_navigation_not_headings():
    html = """<html><body><main><h2>Artificial Intelligence and Data Science</h2>
      <h4>Department Menu</h4>
      <ul><li><a href="/ai-dept/about/"><div><h2>About Department</h2></div></a></li>
          <li><a href="/ai-dept/faculty-list/"><div><h2>Faculty List</h2></div></a></li></ul>
      <table><tr><td>S.No</td><td>Name of the Faculty</td></tr><tr><td>1.</td><td>Dr.M.Karuppasamy</td></tr></table>
      <ul><li><a href="#!"><h4>Respect</h4><p>We respect every member of the college.</p></a></li>
          <li><a href="#!"><h4>Moral Values</h4><p>We uphold moral values.</p></a></li></ul>
    </main></body></html>"""
    doc = extract_html(html, BASE, ALLOWED)
    table = next(b for b in doc.blocks if b.type == "table")
    assert table.heading_path == ["Artificial Intelligence and Data Science"]  # not "Faculty List" / "Department Menu"
    assert not any(b.text in ("About Department", "Faculty List", "Department Menu") for b in doc.blocks)
    assert any(b.text == "Respect" for b in doc.blocks)  # cards with their own text are content
    assert any("/ai-dept/faculty-list/" in link.url for link in doc.links)


def test_banner_heading_stays_the_parent_of_same_level_headings():
    html = """<html><body><main><h2>Civil Engineering</h2><h5>NBA Accredited from 2024 to 2027</h5>
      <h2>ACADEMIC YEAR 2025 - 2026</h2>
      <table><tr><td>S.No</td><td>Name</td></tr><tr><td>1.</td><td>Dr.R.Kumar</td></tr></table>
    </main></body></html>"""
    table = next(b for b in extract_html(html, BASE, ALLOWED).blocks if b.type == "table")
    assert table.heading_path == ["Civil Engineering", "ACADEMIC YEAR 2025 - 2026"]


def test_first_heading_with_its_own_content_is_an_ordinary_section():
    html = """<html><body><main><h2>Vision</h2><p>To be a centre of excellence.</p>
      <h2>Mission</h2><p>Serve the community.</p></main></body></html>"""
    mission = next(b for b in extract_html(html, BASE, ALLOWED).blocks if b.text == "Serve the community.")
    assert mission.heading_path == ["Mission"]


def test_contact_lines_get_labels():
    from rag.extraction.html_extractor import _label_contact_line

    assert _label_contact_line("- enquiry@aaacet.ac.in") == "Email: enquiry@aaacet.ac.in"
    assert _label_contact_line("- 04562-251111, 18004258807") == "Phone: 04562-251111, 18004258807"
    assert _label_contact_line("Kamarajar Educational Road, Amathur - 626 005") == "Address: Kamarajar Educational Road, Amathur - 626 005"
    assert _label_contact_line("Phone: 123 456 7890") == "Phone: 123 456 7890"
    assert _label_contact_line("COUNSELLING CODE : 4680") == "COUNSELLING CODE : 4680"


def test_page_kind_from_wordpress_body_classes():
    def kind(cls):
        return extract_html(f"<html><body class='{cls}'><main><p>Text here.</p></main></body></html>", BASE, ALLOWED).kind

    assert kind("wp-singular post-template-default single single-post") == "news"
    assert kind("wp-singular cse-template-default single single-cse") == "section"
    assert kind("wp-singular page-template-default page") == "page"
    assert extract_pdf_text("x", "https://college.example/a.pdf", "").kind == "document"


def test_common_site_name_is_stripped_from_titles():
    from rag.extraction.boilerplate import strip_common_title_suffix

    site = "AAA College of Engineering & Technology, Sivakasi"
    titles = [f"AAA Hostels – {site}", f"Admission – {site}", f"Placement – 2017 – {site}", "Gallery | Other"]
    docs = [extract_html(f"<html><head><title>{t}</title></head><body><main><p>x y z</p></main></body></html>",
                         f"https://college.example/{i}", ALLOWED) for i, t in enumerate(titles)]
    assert [d.title for d in strip_common_title_suffix(docs)] == ["AAA Hostels", "Admission", "Placement – 2017", "Gallery | Other"]
