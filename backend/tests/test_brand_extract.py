"""Tests for scripts/extract_brand.py on a synthetic page shaped like a typical college site."""

import importlib.util
import sys

import pytest

from rag.config import PROJECT_DIR

spec = importlib.util.spec_from_file_location("extract_brand", PROJECT_DIR / "scripts" / "extract_brand.py")
extract_brand = importlib.util.module_from_spec(spec)
sys.modules["extract_brand"] = extract_brand
spec.loader.exec_module(extract_brand)

BASE = "https://college.example/"
HTML = """<html><head><title>Example College</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;700">
<style>
body { font-family: 'Poppins', sans-serif; color: #333333; }
.top-bar { background-color: #8b0000; color: #fff; }
header.site-header { background: #ffffff; }
.main-menu { background: #0b3d91; }
.main-menu li a { color: #ffffff; }
.main-menu li a:hover, .main-menu li.active a { background-color: #f5a623; }
footer { background-color: #1a1a2e; color: #dddddd; }
h1, h2, .section-title { color: #0b3d91; font-family: 'Merriweather', serif; }
a { color: #0066cc; }
.btn { background: #f5a623; border-radius: 6px; }
</style></head><body>
<div class="top-bar"><a href="/alumni">Alumni</a> <a href="/payment">Online Payment</a> Phone: 04562 123456 info@college.example</div>
<header class="site-header"><a href="/"><img src="/images/college-logo.png" alt="Example College of Engineering"></a>
<img src="/images/naac-logo.png" alt="NAAC Accredited"></header>
<nav class="main-menu"><ul>
<li><a href="/">Home</a></li>
<li><a href="/about">About Us</a><ul><li><a href="/about/vision">Vision</a></li></ul></li>
<li><a href="/admission">Admission</a></li>
<li><a href="/placement">Placement</a></li>
</ul></nav>
<main><h1>Welcome</h1></main>
<footer><p>Example College</p><p>Example Road, Sivakasi</p><p>Virudhunagar District - 626123</p>
<p>Email: info@college.example</p></footer>
</body></html>"""


@pytest.fixture
def measured():
    return extract_brand.build(HTML, BASE, [], None, ["https://fonts.googleapis.com/css2?family=Poppins"])


def test_colour_helpers():
    assert extract_brand.to_hex("#FFF") == "#ffffff"
    assert extract_brand.to_hex("rgb(11, 61, 145)") == "#0b3d91"
    assert extract_brand.to_hex("rgba(0,0,0,0.1)") is None
    assert extract_brand.to_hex("navy") == "#000080"
    assert extract_brand.readable_on("#0b3d91") == "#ffffff"
    assert extract_brand.readable_on("#f5f5f5") == "#111111"


def test_measures_role_colours_and_fonts(measured):
    brand, tokens, _ = measured
    assert tokens["--brand-primary"] == "#0b3d91"
    assert tokens["--brand-nav-bg"] == "#0b3d91" and tokens["--brand-nav-fg"] == "#ffffff"
    assert tokens["--brand-accent"] == "#f5a623"
    assert tokens["--brand-topbar-bg"] == "#8b0000"
    assert tokens["--brand-footer-bg"] == "#1a1a2e" and tokens["--brand-footer-fg"] == "#dddddd"
    assert tokens["--brand-heading"] == "#0b3d91" and tokens["--brand-link"] == "#0066cc"
    assert tokens["--brand-text"] == "#333333"
    assert tokens["--brand-font-body"].startswith("'Poppins'")
    assert tokens["--brand-font-heading"].startswith("'Merriweather'")
    assert tokens["--brand-radius"] == "6px"
    assert brand["fonts"]["stylesheets"] == ["https://fonts.googleapis.com/css2?family=Poppins"]


def test_measures_logo_nav_links_and_contact(measured):
    brand, _, report = measured
    assert brand["measured"] is True
    assert brand["college_name"] == "Example College of Engineering"
    assert any("college-logo.png" in line for line in report)
    assert [i["label"] for i in brand["nav"]] == ["Home", "About Us", "Admission", "Placement"]
    assert brand["nav"][1]["children"] == [{"label": "Vision", "href": "https://college.example/about/vision"}]
    assert {"label": "Alumni", "href": "https://college.example/alumni"} in brand["utility_links"]
    assert brand["contact"]["emails"] == ["info@college.example"]
    assert brand["contact"]["phones"] == ["04562 123456"]
    assert brand["contact"]["address"][-1] == "Virudhunagar District - 626123"
