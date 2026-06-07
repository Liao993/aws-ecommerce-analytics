# ─────────────────────────────────────────────────────────────────
# dag.py — olist_daily_pipeline master DAG
#
# This file is FLOW ONLY. No task logic lives here.
# It wires together task objects returned by the factory functions
# in tasks/ and sets the dependency chain.
#
# Pipeline sequence:
#
#   trigger_glue_crawler
#          ↓
#   run_glue_etl
#          ↓
#   ┌──────────────────────────────────────────┐
#   │         TaskGroup: data_quality          │
#   │  run_gx_olist_orders ─────────────────   │
#   │  run_gx_olist_order_reviews ──────────   │  (parallel)
#   │  run_gx_olist_order_items ────────────   │
#   └──────────────────────────────────────────┘
#          ↓
#   load_to_redshift
#          ↓
#   dbt_staging
#          ↓
#   dbt_intermediate
#          ↓
#   dbt_marts
#          ↓
#   dbt_snapshot
#
# Dependency syntax:
#   task_a >> task_b       → task_b runs after task_a
#   task_a >> [b, c, d]    → b, c, d run in parallel after task_a
#   [b, c, d] >> task_e    → task_e runs after ALL of b, c, d finish
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.utils.task_group import TaskGroup # type: ignore

from callbacks.notify import notify_on_failure
from config import DAG_CONFIG, GX_TABLES
from tasks.dbt_tasks import (
    make_dbt_intermediate_task,
    make_dbt_marts_task,
    make_dbt_snapshot_task,
    make_dbt_staging_task,
)
from tasks.glue_tasks import (
    make_csv_to_parquet_task,
    make_crawler_task,
    make_load_to_redshift_task,
)
from tasks.gx_tasks import make_gx_task

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Default args — applied to every task in the DAG
# ─────────────────────────────────────────────────────────────────

default_args = {
    "owner":              "henry",
    "depends_on_past":    False,
    "start_date":         datetime(2024, 1, 1),    # historical start; catchup=False so only future runs fire
    "retries":            DAG_CONFIG["retries"],
    "retry_delay":        timedelta(minutes=DAG_CONFIG["retry_delay_mins"]),
    "on_failure_callback": notify_on_failure,
    # email_on_failure / email_on_retry intentionally disabled —
    # all alerting routes through on_failure_callback (SNS in Epic 5)
    "email_on_failure":   False,
    "email_on_retry":     False,
}

# ─────────────────────────────────────────────────────────────────
# DAG definition
# ─────────────────────────────────────────────────────────────────

with DAG(
    dag_id          = DAG_CONFIG["dag_id"],
    default_args    = default_args,
    schedule        = DAG_CONFIG["schedule"],
    catchup         = DAG_CONFIG["catchup"],
    max_active_runs = DAG_CONFIG["max_active_runs"],
    tags            = DAG_CONFIG["tags"],
    description     = (
        "End-to-end Olist pipeline: Glue Crawler → CSV→Parquet ETL → "
        "Great Expectations validation → Redshift load → dbt staging → "
        "intermediate → marts → snapshots."
    ),
) as dag:

    # ── Task 1: Glue Crawler ──────────────────────────────────────
    # Refreshes Glue Data Catalog schemas before ETL reads them.
    # GlueCrawlerOperator (not GlueJobOperator) — different AWS API.
    crawler = make_crawler_task()

    # ── Task 2: CSV → Parquet ETL ─────────────────────────────────
    # Converts all 9 raw CSVs to Snappy Parquet in dev/processed/.
    csv_to_parquet = make_csv_to_parquet_task()

    # ── Tasks 3–5: Great Expectations (parallel, in TaskGroup) ────
    # All three GX tasks run concurrently after csv_to_parquet.
    # TaskGroup collapses them in the Graph View under 'data_quality'.
    # In Feature 2.3 these tasks raise NotImplementedError (stub).
    with TaskGroup(group_id="data_quality") as data_quality_group:
        gx_tasks = [make_gx_task(table) for table in GX_TABLES]

    # ── Task 6: Load to Redshift ──────────────────────────────────
    # Runs only after ALL three GX tasks succeed (or are manually cleared).
    load_redshift = make_load_to_redshift_task()

    # ── Tasks 7–10: dbt transformation chain ─────────────────────
    dbt_staging      = make_dbt_staging_task()
    dbt_intermediate = make_dbt_intermediate_task()
    dbt_marts        = make_dbt_marts_task()
    dbt_snapshot     = make_dbt_snapshot_task()

    # ─────────────────────────────────────────────────────────────
    # Dependency chain
    # ─────────────────────────────────────────────────────────────

    # Sequential: crawler must finish before ETL reads the catalog
    crawler >> csv_to_parquet

    # Fan-out: all GX tasks start immediately after csv_to_parquet
    csv_to_parquet >> data_quality_group

    # Fan-in: Redshift load waits for ALL GX tasks to pass
    data_quality_group >> load_redshift

    # Sequential dbt chain: each layer depends on the one before
    load_redshift >> dbt_staging >> dbt_intermediate >> dbt_marts >> dbt_snapshot
