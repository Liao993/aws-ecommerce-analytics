# ─────────────────────────────────────────────────────────────────
# config.py — DAG constants for olist_daily_pipeline
#
# All job names, table names, schedule, and retry settings live here.
# Neither dag.py nor any tasks file contains a hardcoded string.
#
# How to use:
#   from config import DAG_CONFIG, GLUE_JOBS, GX_TABLES, DBT_CONFIG
# ─────────────────────────────────────────────────────────────────

# ── DAG-level settings ────────────────────────────────────────────

DAG_CONFIG = {
    "dag_id":           "olist_daily_pipeline",
    "schedule":         "0 6 * * *",       # 6am daily; set None for manual-only dev runs
    "catchup":          False,             # never backfill missed runs automatically
    "max_active_runs":  1,                 # prevent overlapping pipeline runs
    "retries":          1,
    "retry_delay_mins": 5,
    "tags":             ["olist", "glue", "dbt", "great_expectations"],
}

# ── AWS / Glue ────────────────────────────────────────────────────

AWS_REGION = "ca-central-1"

# Glue Crawler name — registered in terraform/main.tf
GLUE_CRAWLER_NAME = "olist-dev-raw-crawler"

# Glue ETL job names — registered in terraform/main.tf
GLUE_JOBS = {
    "csv_to_parquet":   "olist-csv-to-parquet",
    "load_to_redshift": "olist-load-to-redshift",
}
S3_DOCS_PREFIX = "dev/analytics/gx-docs"

# Airflow AWS Connection ID — set in Airflow UI or via env var
# AIRFLOW_CONN_AWS_DEFAULT must be configured before running the DAG.
# See Feature 2.3 setup guide for exact connection string format.
AWS_CONN_ID = "aws_default"

# ── Great Expectations ────────────────────────────────────────────

# Table names passed to gx_runner.py — must match GX suite names
GX_TABLES = [
    "olist_orders",
    "olist_order_reviews",
    "olist_order_items",
]

# Path inside the Airflow container where gx_runner.py lives.
# This module is a stub in Feature 2.3 — fully implemented in Feature 2.2.
GX_RUNNER_MODULE = "gx.gx_runner"

# ── dbt ───────────────────────────────────────────────────────────

# Name of the dbt Docker container — must match container_name in docker-compose.yml
DBT_CONTAINER_NAME = "olist_dbt"
GX_CONTAINER_NAME  = "olist_gx"
# dbt project directory INSIDE the dbt container (matches working_dir in docker-compose.yml)
DBT_PROJECT_DIR = "/usr/app/dbt"

# dbt profiles directory INSIDE the dbt container
DBT_PROFILES_DIR = "/root/.dbt"

DBT_CONFIG = {
    "container":    DBT_CONTAINER_NAME,
    "project_dir":  DBT_PROJECT_DIR,
    "profiles_dir": DBT_PROFILES_DIR,
    "target":       "dev",
}

# dbt selectors for each pipeline stage
DBT_SELECTORS = {
    "staging":      "staging",
    "intermediate": "intermediate",
    "marts":        "marts",
}
