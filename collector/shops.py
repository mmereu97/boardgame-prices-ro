"""The shops we read, and how. Adding a shop on a known platform is one line here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Shop:
    key: str            # short id used everywhere (files, tables)
    name: str
    base_url: str
    platform: str       # "shopify" | "jsonld_sitemap"
    sitemap: str = ""   # jsonld_sitemap: the products sitemap
    min_delay: float = 2.0


# Shopify rate-limits its public catalogue (HTTP 429 seen in testing), so its shops get
# a longer pause; there are only ~10-30 requests per shop, so this costs a few minutes.
SHOPIFY_DELAY = 10.0


SHOPS = {s.key: s for s in [
    Shop("ludicus", "Ludicus", "https://ludicus.ro", "shopify", min_delay=SHOPIFY_DELAY),
    Shop("redgoblin", "Red Goblin", "https://redgoblin.ro", "shopify", min_delay=SHOPIFY_DELAY),
    Shop("jocozaur", "Jocozaur", "https://jocozaur.ro", "shopify", min_delay=SHOPIFY_DELAY),
    Shop("idealboardgames", "Ideal Board Games", "https://idealboardgames.ro", "shopify", min_delay=SHOPIFY_DELAY),
    # robots.txt asks for Crawl-delay: 5; the session honours it automatically.
    Shop("pionul", "Pionul", "https://www.pionul.ro", "jsonld_sitemap",
         sitemap="https://www.pionul.ro/sitemap_products.xml"),
]}
