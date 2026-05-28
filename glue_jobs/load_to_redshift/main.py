"""
main.py — load_to_redshift Glue job entrypoint (Feature 2.1 — all 9 tables)

What this job does:
    Reads all 9 processed Olist Parquet tables from the Glue Data Catalog
    (olist_dev_processed) and loads each into Redshift dev_raw schema.
    Each table is a full truncate-and-reload — the DDL in config.py runs
    as preactions before each COPY: DROP TABLE IF EXISTS → CREATE TABLE.

    Incremental merge (UPDATE + INSERT on changed rows) is handled by
    dbt in Epic 4, not here.

Fault tolerance:
    Each table runs inside an isolated try/except block. A failure on one
    table logs the full traceback and continues to the next. All failures
    are collected and re-raised at the end so Glue marks the job FAILED
    and Airflow's GlueJobOperator surfaces the error clearly.

Pipeline per table — 6 steps, identical for every table:
    Step 1 — Read processed Parquet from Glue Data Catalog (readers.py)
    Step 2 — Normalize Glue ChoiceType column names (transformers.py)
    Step 3 — Auto-detect and drop S3 partition columns (transformers.py)
    Step 4 — Cast declared timestamp columns to TimestampType (transformers.py)
    Step 5 — Project to exact target columns in config order (transformers.py)
    Step 6 — Write to Redshift via spark-redshift COPY (writers.py)
    Step 7 — Validate post-load row count matches Parquet source (validators.py)

File responsibilities:
    config.py       — all per-table settings: columns, timestamps, DDL
    readers.py      — Glue catalog read → DynamicFrame
    transformers.py — reshape DataFrame: normalize, drop, cast, project
    writers.py      — spark-redshift COPY write only
    validators.py   — post-load row count check via direct JDBC
    main.py         — orchestration: bootstrap, loop, try/except, summary

Auth:
    Glue assumes olist-senior-de-role (trusted principal in main.tf).
    JDBC connection uses REDSHIFT_USER + REDSHIFT_PASSWORD — Redshift
    database login, separate from IAM. Credentials injected at runtime.
"""

import sys
import logging

# pyrefly: ignore [missing-import]
from awsglue.utils import getResolvedOptions
# pyrefly: ignore [missing-import]
from awsglue.context import GlueContext
# pyrefly: ignore [missing-import]
from awsglue.job import Job
# pyrefly: ignore [missing-import]
from pyspark.context import SparkContext

from config import (
    SOURCE_CATALOG_DATABASE,
    PARTITION_HELPER_COLUMNS,
    REDSHIFT_JDBC_DRIVER,
    PARAM_REDSHIFT_URL,
    PARAM_REDSHIFT_USER,
    PARAM_REDSHIFT_PASSWORD,
    PARAM_REDSHIFT_TMP_DIR,
    PARAM_REDSHIFT_S3_ROLE_ARN,
    TABLES,
    full_table_ref,
)
from readers import read_catalog_table
from transformers import (
    normalize_choice_type_columns,
    drop_partition_helper_columns,
    cast_timestamp_columns,
    select_target_columns,
)
from writers import write_to_redshift
from validators import validate_redshift_row_count

# ─────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────
# Glue job bootstrap
# ─────────────────────────────────────────────────────────────────

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    PARAM_REDSHIFT_URL,
    PARAM_REDSHIFT_USER,
    PARAM_REDSHIFT_PASSWORD,
    PARAM_REDSHIFT_TMP_DIR,
    PARAM_REDSHIFT_S3_ROLE_ARN,
])

sc          = SparkContext()
glueContext = GlueContext(sc)
spark       = glueContext.spark_session
job         = Job(glueContext)
job.init(args["JOB_NAME"], args)

redshift_url         = args[PARAM_REDSHIFT_URL]
redshift_user        = args[PARAM_REDSHIFT_USER]
redshift_password    = args[PARAM_REDSHIFT_PASSWORD]
redshift_tmp_dir     = args[PARAM_REDSHIFT_TMP_DIR]
redshift_s3_role_arn = args[PARAM_REDSHIFT_S3_ROLE_ARN]


# ─────────────────────────────────────────────────────────────────
# Per-table pipeline
# ─────────────────────────────────────────────────────────────────

def process_table(table: dict) -> int:
    """
    Full load pipeline for one table. Returns source row count on success.

    Args:
        table: One entry from config.TABLES (plain dict).

    Returns:
        Source Parquet row count — logged in the end-of-job summary.

    Raises:
        Any exception from readers / transformers / writers / validators
        propagates to the calling try/except block in __main__.
    """
    tname = table["source_catalog_table"]
    ref   = full_table_ref(table)

    logger.info(f"{'─' * 60}")
    logger.info(f"Starting: {tname} → {ref}")

    # Step 1 — Read Parquet from Glue catalog
    dyf = read_catalog_table(
        glue_context = glueContext,
        database     = SOURCE_CATALOG_DATABASE,
        table_name   = tname,
    )
    source_row_count = dyf.count()
    logger.info(f"{tname}: source Parquet row count: {source_row_count:,}")

    # Step 2 — Normalize Glue ChoiceType column names
    dyf = normalize_choice_type_columns(
        glue_context = glueContext,
        dyf          = dyf,
        table_name   = tname,
    )

    # Step 3 — Auto-detect and drop S3 partition helper columns
    # No per-table config needed — checks at runtime if column exists.
    dyf = drop_partition_helper_columns(
        glue_context             = glueContext,
        dyf                      = dyf,
        partition_helper_columns = PARTITION_HELPER_COLUMNS,
        table_name               = tname,
    )

    # Step 4 — Cast declared timestamp columns to TimestampType
    # No-op if table["timestamp_columns"] is empty list.
    dyf = cast_timestamp_columns(
        glue_context      = glueContext,
        dyf               = dyf,
        timestamp_columns = table["timestamp_columns"],
        table_name        = tname,
    )

    # Step 5 — Project to exact target columns in DDL order
    dyf = select_target_columns(
        glue_context   = glueContext,
        dyf            = dyf,
        target_columns = table["target_columns"],
        table_name     = tname,
    )

    # Step 6 — Write to Redshift
    # DDL in table["ddl"] runs as preactions: CREATE SCHEMA → DROP TABLE → CREATE TABLE
    write_to_redshift(
        glue_context         = glueContext,
        dyf                  = dyf,
        full_table_ref       = ref,
        ddl                  = table["ddl"],
        redshift_url         = redshift_url,
        redshift_user        = redshift_user,
        redshift_password    = redshift_password,
        redshift_tmp_dir     = redshift_tmp_dir,
        redshift_s3_role_arn = redshift_s3_role_arn,
        table_name           = tname,
    )

    # Step 7 — Post-load row count validation
    validate_redshift_row_count(
        spark             = spark,
        full_table_ref    = ref,
        expected_count    = source_row_count,
        redshift_url      = redshift_url,
        redshift_user     = redshift_user,
        redshift_password = redshift_password,
        jdbc_driver       = REDSHIFT_JDBC_DRIVER,
        table_name        = tname,
    )

    logger.info(f"{tname}: done ✓  ({source_row_count:,} rows)")
    return source_row_count


# ─────────────────────────────────────────────────────────────────
# Entry point — loop all 9 tables, collect failures
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    failed = []   # list of (table_name, error_message)
    loaded = []   # list of (table_name, row_count)

    logger.info(f"Starting load_to_redshift — {len(TABLES)} tables")

    for table in TABLES:
        tname = table["source_catalog_table"]
        try:
            row_count = process_table(table)
            loaded.append((tname, row_count))
        except Exception as exc:
            # Log full traceback but continue — one bad table should not
            # block the remaining tables from loading.
            logger.error(f"FAILED: {tname}: {exc}", exc_info=True)
            failed.append((tname, str(exc)))

    # ── End-of-job summary ────────────────────────────────────────
    logger.info("=" * 60)
    logger.info(f"Completed: {len(loaded)} succeeded / {len(failed)} failed / {len(TABLES)} total")
    for tname, row_count in loaded:
        logger.info(f"  ✓  {tname:<55s}  {row_count:>10,} rows")
    if failed:
        for tname, err in failed:
            logger.error(f"  ✗  {tname}: {err}")
        raise RuntimeError(
            f"load_to_redshift failed for {len(failed)} table(s): "
            f"{[t for t, _ in failed]}"
        )

    logger.info("All tables loaded successfully ✓")
    job.commit()
    logger.info("Job committed ✓")