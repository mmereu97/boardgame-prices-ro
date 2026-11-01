"""Nightly board-game price collection for Romanian shops.

    collect (one task per shop, in parallel)  ->  load into PostgreSQL  ->  dbt build

- Each shop is its own task: a shop that is down or rate-limits us is retried on its own,
  and the others carry on. At most two run at once, and never two Shopify shops together:
  Shopify rate-limits by IP across all the shops it hosts.
- load and dbt run even if some shops failed ("all_done"): yesterday's prices stay valid
  for a shop that failed tonight (see mart_best_prices).
- dbt build runs the models, the price-history snapshot and every test; a failing test
  fails the run, so bad data never reaches the dashboard silently.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PROJECT = Path(os.environ.get("BOARDGAME_PROJECT", "/opt/project"))
RAW = Path(os.environ.get("BOARDGAME_RAW", "/data/raw"))
DBT = os.environ.get("DBT_BIN", "/opt/dbt-venv/bin/dbt")
TZ = "Europe/Bucharest"

sys.path.insert(0, str(PROJECT))
from collector.shops import SHOPS  # noqa: E402


def today_dir() -> Path:
    return RAW / pendulum.now(TZ).to_date_string()


@dag(
    schedule="30 1 * * *",               # 01:30, Romanian time: shops are quiet at night
    start_date=pendulum.datetime(2026, 11, 1, tz=TZ),
    catchup=False,                       # prices of past nights cannot be collected anyway
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=20)},
    tags=["boardgames", "scraping", "dbt"],
    doc_md=__doc__,
)
def boardgame_prices():

    # At most two collections at once: Pionul in one slot, the Shopify shops one after the
    # other in the second. Shopify rate-limits by IP across all its shops (HTTP 429 on the
    # NAS when four ran in parallel), so its shops must not run side by side.
    @task(execution_timeout=timedelta(hours=4), max_active_tis_per_dagrun=2)
    def collect(shop: str) -> str:
        from collector.run import collect as run_collect
        out = today_dir() / f"{shop}.jsonl"
        # BOARDGAME_LIMIT=20 makes a quick smoke test: a few products per shop instead of all
        n = run_collect(shop, out, int(os.environ.get("BOARDGAME_LIMIT") or 0) or None)
        if n == 0:
            raise ValueError(f"{shop}: no products collected")
        return str(out)

    @task(trigger_rule="all_done")
    def load() -> dict:
        import psycopg
        from loader.load_raw import load as load_files
        files = sorted(today_dir().glob("*.jsonl"))
        if not files:
            raise ValueError("no shop delivered data tonight")
        with psycopg.connect() as conn:
            return load_files(files, conn)

    # The project is mounted read-only; dbt writes target/ and logs/, so it runs from a copy.
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(f"rm -rf /tmp/dbt-run && cp -r {PROJECT}/dbt /tmp/dbt-run && "
                      f"cd /tmp/dbt-run && {DBT} build --profiles-dir ."),
        retries=0,                       # a failing data test needs a human, not a retry
    )

    # the long collection (Pionul) starts first, so the Shopify shops queue in the other slot
    order = sorted(SHOPS, key=lambda k: (SHOPS[k].platform == "shopify", k))
    collect.expand(shop=order) >> load() >> dbt_build


boardgame_prices()
