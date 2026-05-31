# ─────────────────────────────────────────────────────────────────
# tasks/glue_tasks.py — Glue Crawler + ETL task definitions
#
# Exports three factory functions:
#   make_crawler_task()    → GlueCrawlerOperator for olist-dev-raw-crawler
#   make_csv_to_parquet_task() → GlueJobOperator for olist-csv-to-parquet
#   make_load_to_redshift_task() → GlueJobOperator for olist-load-to-redshift
#
# Why factory functions instead of module-level task objects?
#   Task objects must be created inside the DAG context manager.
#   Factory functions are called inside `with dag:` in dag.py,
#   which satisfies that requirement and keeps this file importable
#   and testable without an active DAG context.
#
# Why GlueCrawlerOperator for the crawler task?
#   The Glue Crawler and Glue ETL job use different AWS APIs:
#     Crawler → glue.start_crawler()     (no run-time parameters)
#     ETL Job → glue.start_job_run()     (accepts --job-arguments)
#   Using GlueJobOperator for a crawler would call the wrong API
#   and fail with "Job not found". GlueCrawlerOperator is the
#   semantically correct and operationally correct choice.
#
# AWS auth:
#   Both operators use the Airflow Connection aws_default.
#   Set AIRFLOW_CONN_AWS_DEFAULT in your .env file before running.
#   See Feature 2.3 setup guide for the connection string format.
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging

from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator

from config import AWS_CONN_ID, AWS_REGION, GLUE_CRAWLER_NAME, GLUE_JOBS

logger = logging.getLogger(__name__)


def make_crawler_task() -> GlueCrawlerOperator:
    """
    Task 1: Trigger the Glue Crawler and wait for it to finish.

    The crawler re-scans dev/raw/ in S3 and updates the Glue Data Catalog
    schema for any new or changed CSV files. This must complete before
    csv_to_parquet runs — otherwise the ETL job reads stale schemas.

    Operator behaviour:
        GlueCrawlerOperator calls StartCrawler, then polls every 30 seconds
        until the crawler state is READY (success) or FAILED. If the crawler
        is already running from a Lambda trigger, the operator waits for that
        run to finish rather than starting a duplicate.

    Returns:
        GlueCrawlerOperator task object, to be wired into the DAG in dag.py.
    """
    return GlueCrawlerOperator(
        task_id         = "trigger_glue_crawler",
        config              = {"Name": GLUE_CRAWLER_NAME},
        aws_conn_id     = AWS_CONN_ID,
        region_name     = AWS_REGION,
        wait_for_completion = True,
        # poll_interval: check crawler status every 30 seconds
        # default is 5s which generates excessive API calls
        poll_interval   = 30,
    )


def make_csv_to_parquet_task() -> GlueJobOperator:
    """
    Task 2: Run the csv_to_parquet Glue ETL job.

    Reads all 9 Olist CSVs from the Glue Data Catalog (olist_dev_raw)
    and writes Snappy Parquet to s3://olist-ecommerce-tara888/dev/processed/.
    Date-partitioned tables get year=YYYY/month=MM folder structure.

    Operator behaviour:
        GlueJobOperator calls StartJobRun, waits for SUCCEEDED or FAILED,
        then surfaces the CloudWatch log URL on failure. The operator
        raises AirflowException if the job ends in any non-SUCCEEDED state.

    Returns:
        GlueJobOperator task object.
    """
    return GlueJobOperator(
        task_id         = "run_glue_etl",
        job_name        = GLUE_JOBS["csv_to_parquet"],
        aws_conn_id     = AWS_CONN_ID,
        region_name     = AWS_REGION,
        wait_for_completion = True,
        # verbose: stream Glue CloudWatch logs to Airflow task logs
        # extremely useful for debugging — shows PySpark errors inline
        verbose         = True,
    )


def make_load_to_redshift_task() -> GlueJobOperator:
    """
    Task 6: Run the load_to_redshift Glue ETL job.

    Reads processed olist_orders Parquet from Glue Data Catalog,
    drops partition helper columns, and bulk-loads to Redshift
    dev_raw.olist_orders via COPY. Post-load row count validated inside
    the Glue job itself (validators.py).

    This task runs after all three GX tasks complete. If any GX task
    raised NotImplementedError (stub) or a GX failure, this task will
    not start — protecting Redshift from unvalidated data.

    Returns:
        GlueJobOperator task object.
    """
    return GlueJobOperator(
        task_id         = "load_to_redshift",
        job_name        = GLUE_JOBS["load_to_redshift"],
        aws_conn_id     = AWS_CONN_ID,
        region_name     = AWS_REGION,
        wait_for_completion = True,
        verbose         = True,
    )
