"""One reader per shop platform. Each yields raw records; parsing into columns happens in dbt (ELT).

A record is {"url": ..., "payload": {...}}: the payload is kept as the shop published it,
trimmed of heavy fields we never use (descriptions, images), so the raw layer stays honest.
"""
import json
import re
from collections.abc import Iterator

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


READERS = {"shopify": shopify, "jsonld_sitemap": jsonld_sitemap}
