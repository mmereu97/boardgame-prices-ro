# Airflow with the collector's libraries; dbt lives in its own virtualenv, because dbt and
# Airflow pin conflicting dependencies (the setup Astronomer and the dbt docs recommend).
FROM apache/airflow:3.3.2-python3.12

USER airflow
RUN pip install --no-cache-dir "requests>=2.32" "psycopg[binary]>=3.2" \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"

RUN python -m venv /opt/airflow/dbt-venv \
 && /opt/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-core==1.10.23" "dbt-postgres==1.10.2"
