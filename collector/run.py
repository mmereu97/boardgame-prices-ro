"""Collect one shop into a JSON Lines file.

    python -m collector.run ludicus --out data/raw/2026-11-01/ludicus.jsonl [--limit 50]
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .platforms import READERS
from .polite import PoliteSession
from .shops import SHOPS


def collect(shop_key: str, out: Path, limit: int | None = None) -> int:
    shop = SHOPS[shop_key]
    session = PoliteSession(min_delay=shop.min_delay)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".partial")
    n = 0
    with tmp.open("w", encoding="utf-8") as f:
        for rec in READERS[shop.platform](shop, session, limit):
            rec = {"shop": shop.key, "platform": shop.platform,
                   "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(out)   # a half-written file never looks like a finished one
    logging.info("%s: %d records -> %s", shop_key, n, out)
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shop", choices=sorted(SHOPS))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None, help="stop after N products (for tests)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = collect(a.shop, a.out, a.limit)
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
