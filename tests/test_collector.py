"""Collector tests: no network, only saved pages and fake responses."""
import json
from pathlib import Path

import pytest
import requests

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


def test_shopify_reads_one_collection_when_the_shop_has_one():
    from dataclasses import replace
    urls = []

    class Recording(FakeSession):
        def get(self, url, params=None, **kw):
            urls.append(url)
            return super().get(url, params, **kw)

    list(platforms.shopify(replace(SHOP, collection="board-games"), Recording([[product(1)]])))
    list(platforms.shopify(SHOP, Recording([[product(1)]])))
    assert urls == ["https://example.ro/collections/board-games/products.json",
                    "https://example.ro/products.json"]


def test_shopify_shops_take_turns_with_a_cool_down(monkeypatch):
    # Blocked on 02.11.2026 after one shop: the next Shopify shop waits 20 minutes.
    monkeypatch.setattr(platforms.shops, "SHOPIFY_COOLDOWN", 20 * 60)
    pauses = []
    monkeypatch.setattr(platforms.time, "sleep", pauses.append)
    list(platforms.shopify(SHOP, FakeSession([[product(1)]])))
    assert pauses == []                          # nothing ran before it
    list(platforms.shopify(SHOP, FakeSession([[product(2)]])))
    assert len(pauses) == 1 and 19 * 60 < pauses[0] < 20 * 60 + 1


def test_shopify_cool_down_counts_from_a_failed_shop_too(monkeypatch):
    class Blocked429(FakeSession):
        def get(self, url, params=None, **kw):
            raise RuntimeError("429")
    monkeypatch.setattr(platforms.shops, "SHOPIFY_COOLDOWN", 20 * 60)
    pauses = []
    monkeypatch.setattr(platforms.time, "sleep", pauses.append)
    with pytest.raises(RuntimeError):
        list(platforms.shopify(SHOP, Blocked429([])))
    list(platforms.shopify(SHOP, FakeSession([[product(1)]])))
    assert len(pauses) == 1


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


class PrestaShopSession:
    """Serves the saved Regatul listing for the listing URL and the saved product page otherwise."""
    def __init__(self):
        self.listing = json.loads((FIXTURES / "regatul_listing.json").read_text(encoding="utf-8"))
        self.page_html = (FIXTURES / "regatul_product.html").read_text(encoding="utf-8")
        self.product_pages = 0

    def get(self, url, params=None, headers=None, **kw):
        if params is not None:
            assert params["resultsPerPage"] == 100 and headers["X-Requested-With"] == "XMLHttpRequest"
            data = self.listing if params["page"] == 1 else {"products": [], "pagination": {"pages_count": 1}}
            return FakeResponse(data)
        self.product_pages += 1
        return FakeResponse(text=self.page_html)


def regatul(budget=400):
    from collector.shops import SHOPS
    from dataclasses import replace
    return replace(SHOPS["regatuljocurilor"], detail_budget=budget)


class GonePage(PrestaShopSession):
    """Like the real night of 03.11.2026: some product pages answer 404."""
    def __init__(self, gone):
        super().__init__()
        self.gone = gone

    def get(self, url, params=None, headers=None, **kw):
        if params is None and self.product_pages < self.gone:
            self.product_pages += 1
            r = requests.Response(); r.status_code = 404; r.url = url
            raise requests.HTTPError("404 Client Error", response=r)
        return super().get(url, params, headers, **kw)


def test_a_missing_product_page_is_skipped_not_fatal():
    session = GonePage(gone=1)
    records = list(platforms.prestashop(regatul(), session))
    assert len(records) == 5                          # the whole listing is still collected
    assert records[0]["payload"]["gtin13"] is None    # the first game's page was gone
    assert records[1]["payload"]["gtin13"]            # the next ones still get their barcode
    assert platforms.BarcodeCache(platforms.cache_dir() / "regatuljocurilor_barcodes.json").get(records[0]["payload"]["id_product"]) is None


def test_many_broken_product_pages_still_stop_the_shop(monkeypatch):
    monkeypatch.setattr(platforms, "DETAIL_MAX_FAILED", 2)
    with pytest.raises(requests.HTTPError):
        list(platforms.prestashop(regatul(), GonePage(gone=10)))


def test_prestashop_reads_the_listing_and_fetches_barcodes_only_for_games(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDGAME_CACHE", str(tmp_path))
    session = PrestaShopSession()
    records = list(platforms.prestashop(regatul(), session))
    names = [r["payload"]["name"] for r in records]
    assert names[0] == "Scythe (English Edition)" and len(records) == 5
    # four games get a product-page visit; the accessory (Scythe: Modular Board) does not
    assert session.product_pages == 4
    assert records[0]["payload"]["gtin13"] == "0653341025005"
    assert records[-1]["payload"]["reference"] == "Accesoriu" and records[-1]["payload"]["gtin13"] is None
    assert records[0]["payload"]["price_amount"] == 449


def test_prestashop_remembers_barcodes_between_nights(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDGAME_CACHE", str(tmp_path))
    list(platforms.prestashop(regatul(), PrestaShopSession()))
    second_night = PrestaShopSession()
    records = list(platforms.prestashop(regatul(), second_night))
    assert second_night.product_pages == 0
    assert records[0]["payload"]["gtin13"] == "0653341025005"


def test_prestashop_respects_the_nightly_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDGAME_CACHE", str(tmp_path))
    session = PrestaShopSession()
    records = list(platforms.prestashop(regatul(budget=2), session))
    assert session.product_pages == 2
    assert [r["payload"]["gtin13"] is not None for r in records[:4]] == [True, True, False, False]


def test_gomag_listing_reads_prices_and_stock_from_real_boxes():
    boxes = platforms.gomag_listing((FIXTURES / "lexshop_listing.html").read_text(encoding="utf-8"))
    assert len(boxes) == 6
    by_name = {b["name"]: b for b in boxes}
    ants = by_name["March of the Ants Evolved Edition - Joc de Strategie, Engleza"]
    assert ants["price"] == "269.25" and ants["list_price"] == "359.00" and ants["in_stock"] is True
    assert by_name["Wildlands"]["in_stock"] is False                 # "Alerta stoc" = out of stock
    assert any(n.startswith("Jim Henson's Labyrinth") for n in by_name)  # &#039; decoded


class GomagSession:
    def __init__(self):
        self.listing = (FIXTURES / "lexshop_listing.html").read_text(encoding="utf-8")
        self.page_html = (FIXTURES / "lexshop_product.html").read_text(encoding="utf-8")
        self.pages, self.product_pages = [], 0

    def get(self, url, params=None, **kw):
        if params is not None:
            self.pages.append(params["p"])
            return FakeResponse(text=self.listing)   # every page returns the same boxes
        self.product_pages += 1
        return FakeResponse(text=self.page_html)


def test_gomag_stops_when_a_page_brings_nothing_new_and_skips_accessory_pages(tmp_path, monkeypatch):
    from collector.shops import SHOPS
    monkeypatch.setenv("BOARDGAME_CACHE", str(tmp_path))
    session = GomagSession()
    records = list(platforms.gomag(SHOPS["lexshop"], session))
    assert len(records) == 6 and session.pages == [1, 2]
    # the playmat is an accessory: no product-page visit for it
    assert session.product_pages == 5
    assert records[1]["payload"]["gtin13"] == "4002051693732"
