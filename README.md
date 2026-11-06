# 🎲 Board Game Prices RO

**Every night, the board-game prices of seven Romanian shops: collected politely, matched across shops, kept as history, tested, and shown on a dashboard.**

Same game, different names: one shop sells *"Dixit - Joc de societate, editie in limba romana"*, another *"DIXIT (RO)"*, a third *"Dixit, román nyelvű társasjáték"*. This pipeline recognises them as one game, finds the cheapest shop today and tells whether today's price is the lowest ever seen.

**Stack:** Python · Apache Airflow 3 · PostgreSQL · dbt (models, snapshots, data tests, unit tests) · Metabase · Docker Compose · GitHub Actions

```
 shops (public catalogues)          Airflow, every night at 01:30
 ───────────────────────            ──────────────────────────────────────────────────
 Ludicus, Red Goblin,      ──►  collect ×7 (one task per shop, at most 2 at once, polite)
 Jocozaur, Ideal Board          │
 Games (Shopify JSON)           ▼
 Pionul (schema.org        load  ──►  raw.offers (JSONB, one row per product per day)
 data on product pages)         │
 Regatul Jocurilor              │
 (PrestaShop listing JSON       │
 + barcode, once per game)      │
 Lexshop (Gomag category        │
 pages + barcode, once)         │
                                ▼
                          dbt build
                            staging       one shape per platform (jsonb → columns)
                            intermediate  barcode check · title normalisation · game matching
                            marts         fct_offer_prices · dim_games · mart_best_prices
                            snapshot      price history as SCD Type 2
                            tests         20 data tests + 2 unit tests: a failure stops the run
                                │
                                ▼
                            Metabase dashboard
```

## The interesting part: matching the same game across shops

Shops don't share product ids, and their titles disagree. Each offer is assigned to a game by three rules, from most to least certain (`int_offer_game_keys`):

1. **Barcode.** Many shops put the EAN in the SKU field. `util.valid_ean()` verifies the **check digit**, so an internal 13-digit code is not mistaken for a barcode.
2. **Title → barcode.** An offer without a barcode joins the game of an offer with the **same normalised title and the same edition language** that has one.
3. **Title.** No barcode anywhere: the game is identified by its normalised title and language.

`util.match_title()` reduces a title to the game's name: lower case, no diacritics, no *"joc de societate"*, *"editie in limba romana"*, *"board game"*, *"base game"*, nor their Hungarian equivalents (one shop publishes titles in Hungarian). **The edition language is kept separately**: a Romanian and an English edition are different products and are never merged. Hungarian editions (*"magyar nyelvű"*) are recognised too and left out of the marts, since nobody here plays in Hungarian; they stay in the raw layer. A bilingual Hungarian-Romanian edition counts as Romanian.

Both rules are covered by **dbt unit tests** with real title variants, and a data test guarantees that a barcode never ends up in two games.

## Being a good guest on someone else's website

- Only public catalogues that **robots.txt** allows; its **Crawl-delay** is honoured (Pionul asks for 5 s).
- A minimum pause per shop; Shopify shops get a minute between pages, because Shopify answered **HTTP 429** (see below): at 30 s, two pages went through and the third was refused. On 429 the collector backs off exponentially (1, 2, 4, 8 minutes) or longer if the shop asks for it with **Retry-After**. If a shop is still blocked after that, it keeps the pages it has, waits 30 minutes and continues from the same page, up to four times: on 06.11.2026 two shops of 21-22 pages failed all three tries, the last one at page 8 for both, and each try had started over from page 1.
- An honest User-Agent that names the project.
- **Regatul Jocurilor (PrestaShop):** its sitemap has ~14,700 product pages, too many to open every night. The whole catalogue is read instead from the shop's own listing in JSON (the format its pages use when you browse), 100 products per page: about 150 requests, with 4 s between them. The barcode is only on the product page, so the collector opens it **once per game**, at most 400 a night, and remembers the barcodes (`BarcodeCache`); in a few weeks every game has one, and until then it is matched by title.
- **Lexshop (Gomag):** its robots.txt disallows the shop's AJAX product loader, so the collector reads only the normal category pages (about 250 pages of 24, 3 s apart), with prices from each product box's data and stock from its button ("Adauga in cos" or "Alerta stoc"). Barcodes once per game, as for Regatul.
- Barcodes come in two lengths: EAN-13 and, for American games, the 12-digit UPC-A, which is normalised to EAN-13 with a leading zero so the same game matches across shops.
- Shopify shops: one request per 250 products (`/products.json`). Red Goblin sells mostly comics and figurines (about 45,000 products), so only its **Board Games** collection is read (`/collections/board-games/products.json`, about 5,300 products, 22 requests); Jocozaur also sells toys, LEGO and books, so only its all-board-games collection (`tarsasjatekok`) is read. Some shops repeat the last page instead of ending; the collector stops when a page brings nothing new.
- At most two shops are collected at once, and **never two Shopify shops together**: Shopify rate-limits by IP across every shop it hosts. Four shops in parallel from the home server earned an HTTP 429 even on the first page, so the Shopify shops queue one after the other while Pionul (about three hours, at its requested 5 s) runs alongside. That was not enough either: on the second night, one shop at a time with 10 s between pages, the server was blocked for more than an hour after the first big Shopify catalogue. What Shopify counts is how much one IP reads in total, so its shops now take turns through a lock file with a **20-minute cool-down** between them, and a Shopify shop that still fails is retried an hour later.

## Reliability

- **Idempotent loads:** re-loading a shop's day replaces it, so a re-run never duplicates rows.
- A product page that is gone (HTTP 404, seen at Regatul Jocurilor on the third night) or broken is skipped with a warning instead of failing the whole shop; more than 20 in one night still stops the task, because then the shop itself has a problem.
- A shop that fails tonight is retried on its own, an hour later, while the others carry on. The dashboard keeps that shop's **last known prices** instead of losing them.
- Mapped tasks are labelled with the shop (`collect [jocozaur]`). Airflow identifies them by position, so the shop order must not change while a run is in progress: on the first night a reordering mid-run made a retry collect the wrong shop.
- `dbt build` runs every model, the snapshot and every test. **A failing test fails the run**, so bad data never reaches the dashboard silently.
- **CI** (GitHub Actions) runs the collector tests on saved pages (no network), then the whole pipeline on two days of sample data in a real PostgreSQL, and checks that the snapshot recorded the price change between the two days.

## What is published (and what is not)

The code, the tests and a 24-record sample. **The collected data is not**: it stays in the database of whoever runs the pipeline. This is a personal price tracker, not a price-comparison service.

## Run it

```bash
cp .env.example .env          # set a password and the data folder
docker compose up -d --build
```

- Airflow: http://localhost:8090. User `admin`; the password is generated on the first start, in `<DATA_DIR>/airflow/passwords.json`.
- Metabase: http://localhost:3010. Connect it to the `boardgames` database (host `postgres`), then build on `marts.mart_best_prices`.

The DAG runs every night at 01:30. For a quick test with only a few products per shop, set `BOARDGAME_LIMIT=20` on the Airflow service.

**Without Docker** (development):

```bash
pip install -r requirements.txt
export PGHOST=localhost PGUSER=postgres PGPASSWORD=... PGDATABASE=boardgames
python -m collector.run ludicus --out data/raw/2026-11-01/ludicus.jsonl
python -m loader.load_raw data/raw/2026-11-01/*.jsonl
cd dbt && dbt build --profiles-dir .
```

## Project layout

| Path | What |
|---|---|
| `collector/` | polite HTTP session, one reader per platform (Shopify JSON, schema.org pages), the shop list |
| `loader/` | JSON Lines → `raw.offers` (JSONB), idempotent per shop and day |
| `dbt/` | staging, intermediate and mart models, the price snapshot, data tests, unit tests, seeds |
| `dags/` | the Airflow DAG |
| `docker/`, `docker-compose.yml` | Airflow image (dbt in its own virtualenv); a `db-init` step creates the Airflow and Metabase databases |
| `tests/`, `sample/` | collector tests on saved pages, sample data for CI |

## Related

[ups-battery-lakehouse](https://github.com/mmereu97/ups-battery-lakehouse) solves a similar problem (crawling shops, normalising messy specs, price history) on **Databricks** with PySpark and Delta Lake. Same kind of problem, two stacks: a lakehouse when the data and the team grow, an open-source pipeline on a small server when they don't.

## Author

Mihai Mereu · [GitHub](https://github.com/mmereu97)
