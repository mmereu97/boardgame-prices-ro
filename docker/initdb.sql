-- Runs once, when the PostgreSQL volume is created: one server, three databases.
create database airflow;    -- Airflow's own metadata
create database metabase;   -- Metabase's settings and dashboards
-- "boardgames" (the data) is created by POSTGRES_DB in docker-compose.yml
