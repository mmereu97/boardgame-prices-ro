"""The shops we read, and how. Adding a shop on a known platform is one line here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Shop:
    key: str                  # short id used everywhere (files, tables)
    name: str
    base_url: str
    platform: str             # "shopify" | "jsonld_sitemap" | "prestashop" | "gomag"
    sitemap: str = ""         # jsonld_sitemap: the products sitemap
    collection: str = ""      # shopify: read only this collection instead of the whole catalogue
    listing_url: str = ""     # prestashop / gomag: the category listing the products we want
    detail_budget: int = 0    # prestashop / gomag: at most this many product pages per night
    detail_types: tuple = ()  # prestashop: product types worth a product-page visit
    min_delay: float = 2.0


# Shopify rate-limits its public catalogue by IP across all its shops: on 02.11.2026, with
# 10 s between pages and one shop at a time, the NAS was still blocked (HTTP 429) for more
# than an hour after Ludicus. What counts is how much one IP reads in total, so its shops
# get 30 s between pages and a cool-down between two shops (see platforms.shopify).
SHOPIFY_DELAY = 30.0
SHOPIFY_COOLDOWN = 20 * 60   # seconds between the end of one Shopify shop and the next


SHOPS = {s.key: s for s in [
    Shop("ludicus", "Ludicus", "https://ludicus.ro", "shopify", min_delay=SHOPIFY_DELAY),
    # Red Goblin sells mostly comics and figurines (~45,000 products, 180 pages): only its
    # Board Games collection (~5,300 products, 22 pages) is read.
    Shop("redgoblin", "Red Goblin", "https://redgoblin.ro", "shopify", collection="board-games",
         min_delay=SHOPIFY_DELAY),
    Shop("jocozaur", "Jocozaur", "https://jocozaur.ro", "shopify", min_delay=SHOPIFY_DELAY),
    Shop("idealboardgames", "Ideal Board Games", "https://idealboardgames.ro", "shopify", min_delay=SHOPIFY_DELAY),
    # robots.txt asks for Crawl-delay: 5; the session honours it automatically.
    Shop("pionul", "Pionul", "https://www.pionul.ro", "jsonld_sitemap",
         sitemap="https://www.pionul.ro/sitemap_products.xml"),
    # The whole catalogue (~14,700 products) in ~150 listing pages of 100; the barcode is only
    # on the product page, so it is fetched once per game and remembered.
    Shop("regatuljocurilor", "Regatul Jocurilor", "https://regatuljocurilor.ro", "prestashop",
         listing_url="https://regatuljocurilor.ro/ro/acasa", detail_budget=400,
         detail_types=("Joc de baza", "Jocul de baza", "Joc de baza + Extensie", "Extensie", "Extensii", "Promo"),
         min_delay=4.0),
    # Gomag: the board-games category in ~250 pages of 24; its AJAX loader is disallowed by
    # robots.txt, so only the normal pages are read. Barcodes once per game, as above.
    Shop("lexshop", "Lexshop", "https://www.lexshop.ro", "gomag",
         listing_url="https://www.lexshop.ro/board-games-3", detail_budget=400, min_delay=3.0),
]}
