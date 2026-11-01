"""Load collected JSON Lines into raw.offers (one row per product per shop per day).

    python -m loader.load_raw data/raw/2026-11-01/ludicus.jsonl [more files...]

Idempotent: re-loading a shop's file for the same day replaces that day, so a re-run of the
pipeline never duplicates rows. Connection settings come from the standard PG* variables.
"""
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

DDL = """
create schema if not exists raw;
create table if not exists raw.offers (
    shop          text        not null,
    platform      text        not null,
    collected_on  date        not null,   -- the shop's day, Europe/Bucharest
    collected_at  timestamptz not null,
    url           text        not null,
    payload       jsonb       not null,
    loaded_at     timestamptz not null default now()
);
create index if not exists offers_shop_day on raw.offers (shop, collected_on);
"""
RO = ZoneInfo("Europe/Bucharest")


def load(paths: list[Path], conn: psycopg.Connection) -> dict:
    by_key = defaultdict(list)
    for path in paths:
        with path.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                at = datetime.fromisoformat(rec["collected_at"])
                by_key[(rec["shop"], at.astimezone(RO).date())].append((rec, at))
    counts = {}
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(DDL)
        for (shop, day), rows in by_key.items():
            cur.execute("delete from raw.offers where shop = %s and collected_on = %s", (shop, day))
            with cur.copy("copy raw.offers (shop, platform, collected_on, collected_at, url, payload) from stdin") as cp:
                for rec, at in rows:
                    cp.write_row((shop, rec["platform"], day, at, rec["url"],
                                  json.dumps(rec["payload"], ensure_ascii=False)))
            counts[f"{shop} {day}"] = len(rows)
    return counts


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    paths = [Path(p) for p in (argv or sys.argv[1:])]
    if not paths:
        print(__doc__)
        return 2
    with psycopg.connect() as conn:
        for key, n in load(paths, conn).items():
            logging.info("loaded %s: %d rows", key, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
