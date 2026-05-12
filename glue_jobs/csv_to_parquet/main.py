"""
csv_to_parquet.py — Glue job entrypoint

Reads all 9 Olist raw CSV tables from the Glue Data Catalog and writes
them to S3 as Snappy-compressed Parquet. Date-partitioned tables get
year/month folder structure for Athena partition pruning. Dimension
tables are written flat.

Failure handling: each table is processed in an isolated try/except block
so a single bad table does not block the remaining 8. All failures are
collected and re-raised at the end so Glue marks the job as FAILED and
Airflow's GlueJobOperator surfaces the error.

Shared helpers:
    shared.readers  → read_catalog_table()
    shared.writers  → resolve_and_clean(), add_partition_columns(), write_parquet()
    shared.csv_to_parquet_config → ALL_TABLES, PARTITIONED_TABLES, SOURCE_DATABASE,
                                   TARGET_S3_PREFIX
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
from awsglue.dynamicframe import DynamicFrame
# pyrefly: ignore [missing-import]
from pyspark.context import SparkContext

from readers import read_catalog_table
from transformers import resolve_and_clean, add_partition_columns
from writers import write_parquet
from config import ALL_TABLES, PARTITIONED_TABLES, SOURCE_DATABASE, TARGET_S3_PREFIX

# ─────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────
# Glue job bootstrap
# ─────────────────────────────────────────────────────────────────

args = getResolvedOptions(sys.argv, ["JOB_NAME"])

sc          = SparkContext()
glueContext = GlueContext(sc)
spark       = glueContext.spark_session
job         = Job(glueContext)
job.init(args["JOB_NAME"], args)


# ─────────────────────────────────────────────────────────────────
# Per-table processing
# ─────────────────────────────────────────────────────────────────

def process_table(table_name: str) -> None:
    """
    Full pipeline for one table:
      1. Read from Glue Data Catalog
      2. Resolve ChoiceType columns + drop null fields
      3. Add partition columns if this is a date-partitioned table
      4. Write to S3 as Parquet and update the Data Catalog
    """
    # Step 1 — Read (raises RuntimeError on zero rows)
    dyf = read_catalog_table(glueContext, SOURCE_DATABASE, table_name)

    # Step 2 — Resolve and clean
    dyf = resolve_and_clean(dyf, table_name)

    # Step 3 — Partition columns (date-partitioned tables only)
    if table_name in PARTITIONED_TABLES:
        date_col = PARTITIONED_TABLES[table_name]
        logger.info(f"{table_name}: partitioning on '{date_col}'")

        df  = dyf.toDF()
        df  = add_partition_columns(df, date_col)
        dyf = DynamicFrame.fromDF(df, glueContext, f"partitioned_{table_name}")

        partition_keys = ["partition_year", "partition_month"]
    else:
        partition_keys = []

    # Step 4 — Write Parquet to S3
    write_parquet(
        glue_context     = glueContext,
        dyf              = dyf,
        table_name       = table_name,
        target_s3_prefix = TARGET_S3_PREFIX,
        source_database  = SOURCE_DATABASE,
        partition_keys   = partition_keys,
    )

    logger.info(f"{table_name}: done ✓")


# ─────────────────────────────────────────────────────────────────
# Entry point — loop all tables, collect failures
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failed: list[str] = []

    for table in ALL_TABLES:
        try:
            process_table(table)
        except Exception as e:
            # Log and continue — one bad table shouldn't block the other 8.
            # Great Expectations in the next DAG step will surface data issues.
            logger.error(f"FAILED processing {table}: {e}", exc_info=True)
            failed.append(table)

    if failed:
        logger.error(f"Job completed with failures: {failed}")
        raise RuntimeError(f"ETL failed for tables: {failed}")

    logger.info("All tables processed successfully.")

    # Required — registers this run as complete in Glue's bookmark store.
    # Without this, Glue marks the job as incomplete in the console even
    # if the Python process exited cleanly.
    job.commit()
