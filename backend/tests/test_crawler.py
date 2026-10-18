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
    no_pdf = AaacetSpider(start_urls=[], allowed_domains=["aaaenggcoll.ac.in"], include_pdfs=False)
    assert not no_pdf._should_follow("https://aaaenggcoll.ac.in/notice.pdf")


def test_crawl_of_demo_site(pipeline):
    pages = [json.loads(line) for line in pipeline.settings.pages_file.read_text().splitlines()]
    urls = {p["url"].replace(pipeline.base_url, "") for p in pages}
    assert {"/", "/about.html", "/admissions.html", "/contact.html", "/placements.html", "/facilities.html",
            "/departments/computer-science.html", "/notices/prospectus.pdf"} <= urls
    assert not any(u.startswith("/private") for u in urls), "robots.txt Disallow must be respected"
    assert not any("assets" in u for u in urls), "binary assets are not crawled as pages"
    assert len(urls) == len(pages), "no duplicate URLs"
    pdf = next(p for p in pages if p["url"].endswith(".pdf"))
    assert pdf["content_type"] == "application/pdf" and "anti-ragging" in pdf["text"]
    status = json.loads(pipeline.settings.status_file.read_text())
    assert status["crawl"]["state"] == "finished" and status["crawl"]["pages"] == len(pages)
