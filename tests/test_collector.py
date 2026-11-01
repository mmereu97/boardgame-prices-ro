"""Collector tests: no network, only saved pages and fake responses."""
from pathlib import Path

import pytest

from collector import platforms
from collector.polite import Blocked, PoliteSession
from collector.shops import Shop

FIXTURES = Path(__file__).parent / "fixtures"


def test_product_jsonld_reads_a_real_pionul_page():
    product = platforms.product_jsonld((FIXTURES / "pionul_dixit.html").read_text(encoding="utf-8"))
    assert product["name"] == "Dixit"
    assert product["offers"]["price"] == 159
    assert product["offers"]["priceCurrency"] == "RON"
    assert product["category"].startswith("Jocuri >")


def test_product_jsonld_ignores_pages_without_product_data():
    assert platforms.product_jsonld("<html><script type='application/ld+json'>{\"@type\": \"WebSite\"}</script></html>") is None
    assert platforms.product_jsonld("<html><script type='application/ld+json'>{not json</script></html>") is None


class FakeResponse:
    def __init__(self, data=None, text=""):
        self._data, self.text = data, text

    def json(self):
        return self._data


class FakeSession:
    """Returns the queued pages in order and records what was asked."""
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, url, params=None, **kw):
        self.calls.append(params)
        return FakeResponse({"products": self.pages.pop(0) if self.pages else []})


def product(i):
    return {"id": i, "handle": f"p{i}", "title": f"Game {i}", "body_html": "<p>long</p>",
            "images": [1], "options": [], "variants": [{"id": i * 10, "price": "10.00", "featured_image": {}}]}


SHOP = Shop("test", "Test", "https://example.ro", "shopify")


def test_shopify_stops_on_a_short_page(monkeypatch):
    monkeypatch.setattr(platforms, "SHOPIFY_PAGE_SIZE", 2)
    session = FakeSession([[product(1), product(2)], [product(3)]])
    records = list(platforms.shopify(SHOP, session))
    assert [r["payload"]["id"] for r in records] == [1, 2, 3]
    assert len(session.calls) == 2


def test_shopify_stops_when_a_shop_keeps_repeating_the_last_page(monkeypatch):
    # Seen in the wild: past the last page some shops return products again instead of [].
    monkeypatch.setattr(platforms, "SHOPIFY_PAGE_SIZE", 2)
    session = FakeSession([[product(1), product(2)], [product(1), product(2)], [product(3), product(4)]])
    records = list(platforms.shopify(SHOP, session))
    assert [r["payload"]["id"] for r in records] == [1, 2]


def test_shopify_drops_heavy_fields_but_keeps_the_raw_record():
    session = FakeSession([[product(1)]])
    rec = next(platforms.shopify(SHOP, session))
    assert rec["url"] == "https://example.ro/products/p1"
    assert "body_html" not in rec["payload"] and "images" not in rec["payload"]
    assert "featured_image" not in rec["payload"]["variants"][0]
    assert rec["payload"]["variants"][0]["price"] == "10.00"


def test_polite_session_refuses_what_robots_txt_disallows(monkeypatch):
    s = PoliteSession(min_delay=0)

    def fake_get(url, timeout=None, **kw):
        assert url.endswith("/robots.txt"), "only robots.txt may be fetched"
        r = FakeResponse(text="User-agent: *\nDisallow: /cart\nCrawl-delay: 5\n")
        r.ok = True
        return r

    monkeypatch.setattr(s.http, "get", fake_get)
    with pytest.raises(Blocked):
        s.get("https://example.ro/cart/1")
    assert s.delay_for("https://example.ro/products/1") == 5


def test_polite_session_backs_off_exponentially_on_429(monkeypatch):
    import collector.polite as polite
    s = PoliteSession(min_delay=0)
    s._robots["https://example.ro"] = polite.urllib.robotparser.RobotFileParser()
    s._robots["https://example.ro"].parse([])
    answers = [429, 429, 429, 200]

    def fake_get(url, timeout=None, **kw):
        r = FakeResponse(text="ok")
        r.status_code = answers.pop(0)
        r.headers = {"Retry-After": "30"}
        r.raise_for_status = lambda: None
        return r

    pauses = []
    monkeypatch.setattr(s.http, "get", fake_get)
    monkeypatch.setattr(polite.time, "sleep", pauses.append)
    assert s.get("https://example.ro/products.json").text == "ok"
    # Retry-After asks for 30 s, but a blocked IP needs longer: 1, 2, 4 minutes
    assert [p for p in pauses if p > 1] == [60, 120, 240]
