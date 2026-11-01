"""One reader per shop platform. Each yields raw records; parsing into columns happens in dbt (ELT).

A record is {"url": ..., "payload": {...}}: the payload is kept as the shop published it,
trimmed of heavy fields we never use (descriptions, images), so the raw layer stays honest.
"""
import html as htmllib
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

from .polite import PoliteSession
from .shops import Shop

SHOPIFY_PAGE_SIZE = 250            # the maximum Shopify allows
SHOPIFY_DROP = ("body_html", "images", "options")


def shopify(shop: Shop, session: PoliteSession, limit: int | None = None) -> Iterator[dict]:
    """Public catalogue at /products.json, 250 products per request.

    Some shops do not answer past the last page with an empty list but keep returning
    products, so we also stop on a short page or on a page that brings nothing new.
    """
    seen: set[int] = set()
    page = 1
    while True:
        r = session.get(f"{shop.base_url}/products.json",
                        params={"limit": SHOPIFY_PAGE_SIZE, "page": page})
        products = r.json().get("products", [])
        new = [p for p in products if p["id"] not in seen]
        for p in new:
            seen.add(p["id"])
            for k in SHOPIFY_DROP:
                p.pop(k, None)
            for v in p.get("variants", []):
                v.pop("featured_image", None)
            yield {"url": f"{shop.base_url}/products/{p['handle']}", "payload": p}
            if limit and len(seen) >= limit:
                return
        if len(products) < SHOPIFY_PAGE_SIZE or not new:
            return
        page += 1


LOC = re.compile(r"<loc>(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?</loc>")
LDJSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def product_jsonld(html: str) -> dict | None:
    """The schema.org Product object embedded in a product page, if any."""
    for block in LDJSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for obj in data.get("@graph", [data]) if isinstance(data, dict) else data:
            if isinstance(obj, dict) and "Product" in str(obj.get("@type", "")):
                return obj
    return None


def jsonld_sitemap(shop: Shop, session: PoliteSession, limit: int | None = None) -> Iterator[dict]:
    """Product URLs from the sitemap, then the schema.org Product data on each page."""
    urls = LOC.findall(session.get(shop.sitemap).text)
    for i, url in enumerate(urls):
        if limit and i >= limit:
            return
        product = product_jsonld(session.get(url).text)
        if product:
            product.pop("description", None)
            yield {"url": url, "payload": product}


PRESTASHOP_PAGE_SIZE = 100
PRESTASHOP_KEEP = ("id_product", "name", "url", "reference", "price", "price_amount",
                   "regular_price_amount", "has_discount", "add_to_cart_url")
JSON_LISTING = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}


class BarcodeCache:
    """Barcodes already read from product pages, kept between runs in one JSON file.

    "" means "the page had no barcode": it is remembered too, so the page is not fetched again.
    """
    def __init__(self, path: Path):
        self.path = path
        self.codes: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def get(self, product_id) -> str | None:
        return self.codes.get(str(product_id))

    def put(self, product_id, code: str | None):
        self.codes[str(product_id)] = code or ""

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.codes, indent=0))
        tmp.replace(self.path)


def cache_dir() -> Path:
    return Path(os.environ.get("BOARDGAME_CACHE", "data/cache"))


def prestashop(shop: Shop, session: PoliteSession, limit: int | None = None) -> Iterator[dict]:
    """The whole catalogue from one listing as JSON (the shop's own AJAX format), 100 per page.

    The listing has price, list price, type and stock (no add-to-cart link = out of stock), but
    no barcode. That is on the product page, so each night at most detail_budget new games get
    a product-page visit, and their barcodes are remembered (BarcodeCache).
    """
    cache = BarcodeCache(cache_dir() / f"{shop.key}_barcodes.json")
    budget = shop.detail_budget
    seen: set = set()
    page = 1
    try:
        while True:
            data = session.get(shop.listing_url, headers=JSON_LISTING,
                               params={"page": page, "resultsPerPage": PRESTASHOP_PAGE_SIZE}).json()
            products = data.get("products", [])
            new = [p for p in products if p["id_product"] not in seen]
            for p in new:
                seen.add(p["id_product"])
                rec = {k: p.get(k) for k in PRESTASHOP_KEEP}
                code = cache.get(p["id_product"])
                if code is None and budget > 0 and p.get("reference") in shop.detail_types:
                    detail = product_jsonld(session.get(p["url"]).text) or {}
                    code = detail.get("gtin13") or detail.get("gtin") or ""
                    cache.put(p["id_product"], code)
                    budget -= 1
                    if budget % 50 == 0:
                        cache.save()
                rec["gtin13"] = code or None
                yield {"url": p["url"], "payload": rec}
                if limit and len(seen) >= limit:
                    return
            if not new or page >= data.get("pagination", {}).get("pages_count", page):
                return
            page += 1
    finally:
        cache.save()


GOMAG_BOX = re.compile(r'<div\s+class="product-box\s')   # the shop's HTML has newlines and double spaces here
GOMAG_PRICES = re.compile(r"data-Gomag='(\{[^']*\})'")
GOMAG_ID = re.compile(r'data-product-id="(\d+)"')
GOMAG_TITLE = re.compile(r'data-block="ListingName"[^>]*>([^<]+)</a>|class="title[^"]*"[^>]*>([^<]+)</a>')
GOMAG_URL = re.compile(r'href="([^"]+\.html)"')
GOMAG_LAST_PAGE = re.compile(r'[?&]p=(\d+)')
# Words that mark accessories inside the shop's board-games category (sleeves, mats...).
ACCESSORY_WORDS = re.compile(r"protecti|sleeve|playmat|insert|organiz|zaruri|dice|deck box|suport|album|binder", re.I)


def gomag_listing(html: str) -> list[dict]:
    """The product boxes of one Gomag category page: id, title, url, prices, stock.

    Prices come from the box's data-Gomag JSON; stock from its button: "Adauga in cos" is in
    stock, "Alerta stoc" (alert me when it is back) is out of stock.
    """
    starts = [m.start() for m in GOMAG_BOX.finditer(html)]
    boxes = []
    for i, start in enumerate(starts):
        box = html[start:starts[i + 1] if i + 1 < len(starts) else start + 20000]
        pid, prices, url = GOMAG_ID.search(box), GOMAG_PRICES.search(box), GOMAG_URL.search(box)
        title = GOMAG_TITLE.search(box)
        if not (pid and prices and url and title):
            continue
        p = json.loads(prices.group(1))
        boxes.append({
            "id": pid.group(1),
            "name": htmllib.unescape(title.group(1) or title.group(2)).strip(),
            "url": url.group(1),
            "price": p.get("Lei_final_price"),
            "list_price": p.get("Lei_price"),
            "in_stock": "Adauga in cos" in box and "Alerta stoc" not in box,
        })
    return boxes


def gomag(shop: Shop, session: PoliteSession, limit: int | None = None) -> Iterator[dict]:
    """A whole Gomag category from its normal pages (?p=1, 2, ...), 24 products per page.

    The shop's robots.txt disallows its AJAX product loader, so only the HTML pages are read.
    As for PrestaShop, the barcode is on the product page: read once per game, remembered.
    """
    cache = BarcodeCache(cache_dir() / f"{shop.key}_barcodes.json")
    budget = shop.detail_budget
    seen: set = set()
    page, last = 1, None
    try:
        while True:
            html = session.get(shop.listing_url, params={"p": page}).text
            if last is None:
                last = max((int(n) for n in GOMAG_LAST_PAGE.findall(html)), default=1)
            new = [b for b in gomag_listing(html) if b["id"] not in seen]
            for b in new:
                seen.add(b["id"])
                code = cache.get(b["id"])
                if code is None and budget > 0 and not ACCESSORY_WORDS.search(b["name"]):
                    detail = product_jsonld(session.get(b["url"]).text) or {}
                    code = detail.get("gtin13") or detail.get("gtin") or ""
                    cache.put(b["id"], code)
                    budget -= 1
                    if budget % 50 == 0:
                        cache.save()
                b["gtin13"] = code or None
                yield {"url": b["url"], "payload": b}
                if limit and len(seen) >= limit:
                    return
            if not new or page >= last:
                return
            page += 1
    finally:
        cache.save()


READERS = {"shopify": shopify, "jsonld_sitemap": jsonld_sitemap, "prestashop": prestashop, "gomag": gomag}
