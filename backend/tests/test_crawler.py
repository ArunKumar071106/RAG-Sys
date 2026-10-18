import json

from rag.crawler.spider import AaacetSpider


def test_spider_url_filter():
    spider = AaacetSpider(start_urls=["https://aaaenggcoll.ac.in/"], allowed_domains=["aaaenggcoll.ac.in"], include_pdfs=True)
    assert spider._should_follow("https://aaaenggcoll.ac.in/about-us")
    assert spider._should_follow("https://www.aaaenggcoll.ac.in/notice.pdf")
    assert not spider._should_follow("https://facebook.com/aaacet")
    assert not spider._should_follow("https://aaaenggcoll.ac.in/wp-admin/x")
    assert not spider._should_follow("https://aaaenggcoll.ac.in/images/photo.JPG")
    assert not spider._should_follow("https://aaaenggcoll.ac.in/brochure.docx")
    assert not spider._should_follow("mailto:x@y.z")
    assert not spider._should_follow("https://aaaenggcoll.ac.in/category/news/")
    assert not spider._should_follow("https://aaaenggcoll.ac.in/latest-updates/page/3/")
    assert not spider._should_follow("https://aaaenggcoll.ac.in/cdn-cgi/l/email-protection")
    for archive in ("2025/", "2025/10/", "2021/04/02/"):  # WordPress date archives
        assert not spider._should_follow(f"https://aaaenggcoll.ac.in/{archive}")
    assert spider._should_follow("https://aaaenggcoll.ac.in/2025-batch-results/")
    no_pdf = AaacetSpider(start_urls=[], allowed_domains=["aaaenggcoll.ac.in"], include_pdfs=False)
    assert not no_pdf._should_follow("https://aaaenggcoll.ac.in/notice.pdf")


def test_crawl_of_demo_site(pipeline):
    pages = [json.loads(line) for line in pipeline.settings.pages_file.read_text().splitlines()]
    urls = {p["url"].replace(pipeline.base_url, "") for p in pages}
    assert {"/", "/about.html", "/admissions.html", "/contact.html", "/placements.html", "/facilities.html",
            "/departments/computer-science.html", "/notices/prospectus.pdf"} <= urls
    assert "/notices/holiday-list.html" in urls, "pages listed only in the sitemap must be crawled"
    assert not any(u.startswith("/private") for u in urls), "robots.txt Disallow must be respected (even via sitemap)"
    assert not any("assets" in u for u in urls), "binary assets are not crawled as pages"
    assert len(urls) == len(pages), "no duplicate URLs"
    pdf = next(p for p in pages if p["url"].endswith(".pdf"))
    assert pdf["content_type"] == "application/pdf" and "anti-ragging" in pdf["text"]
    status = json.loads(pipeline.settings.status_file.read_text())
    assert status["crawl"]["state"] == "finished" and status["crawl"]["pages"] == len(pages)


def test_sitemap_priority_puts_main_pages_first():
    p = AaacetSpider._sitemap_priority
    assert p("https://x/wp-sitemap-posts-page-1.xml") > p("https://x/wp-sitemap-posts-cse-1.xml") > p("https://x/wp-sitemap-posts-post-1.xml")


def test_crawl_specific_urls_merges_into_existing_pages(pipeline, tmp_path):
    import shutil

    from rag.pipeline import run_crawl_subprocess
    from tests.conftest import make_settings

    settings = make_settings(tmp_path / "data", crawl_start_urls=[pipeline.base_url + "/"])
    settings.ensure_dirs()
    original = [json.loads(line) for line in pipeline.settings.pages_file.read_text().splitlines()]
    kept = [p for p in original if not p["url"].endswith("/contact.html")]
    settings.pages_file.write_text("".join(json.dumps(p) + "\n" for p in kept))
    urls = tmp_path / "urls.txt"
    urls.write_text(pipeline.base_url + "/contact.html\n")
    run_crawl_subprocess(settings, str(urls))
    merged = {json.loads(line)["url"] for line in settings.pages_file.read_text().splitlines()}
    assert merged == {p["url"] for p in original}  # the missing page is back, nothing else lost or added
