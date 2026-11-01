"""One reader per shop platform. Each yields raw records; parsing into columns happens in dbt (ELT).

A record is {"url": ..., "payload": {...}}: the payload is kept as the shop published it,
trimmed of heavy fields we never use (descriptions, images), so the raw layer stays honest.
"""
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


READERS = {"shopify": shopify, "jsonld_sitemap": jsonld_sitemap, "prestashop": prestashop}
