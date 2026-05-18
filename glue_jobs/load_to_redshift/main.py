"""
main.py — load_to_redshift Glue job entrypoint

What this job does (Feature 1.5):
    Reads the processed olist_orders Parquet from the Glue Data Catalog,
    drops partition helper columns (added by csv_to_parquet for Athena),
    and loads the clean data into Redshift Serverless using a bulk COPY.
    A post-load row count check confirms the COPY landed correctly.

Where this fits in the pipeline:
    csv_to_parquet/main.py (CSV → Parquet in dev/processed/)
        → Athena validation (manual row count check)
        → THIS JOB (Parquet → Redshift dev_raw.olist_orders)
        → dbt stg_orders model reads from dev_raw schema

How auth works:
    1. Glue assumes olist-senior-de-role (via role_arn in Terraform)
    2. That role gives the job S3 access (read Parquet, write tmp/) and
       Redshift IAM access (allows the COPY command)
    3. The JDBC connection uses REDSHIFT_USER + REDSHIFT_PASSWORD —
       the Redshift database login, separate from IAM entirely

Credentials:
    REDSHIFT_URL, REDSHIFT_USER, REDSHIFT_PASSWORD are never in code.
    They are injected at runtime from Glue job parameters in main.tf.
"""

import sys
import logging

from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

from readers import read_catalog_table
from writers import drop_partition_helper_columns, write_to_redshift
from validators import validate_redshift_row_count
from config import (
    SOURCE_CATALOG_DATABASE,
    SOURCE_CATALOG_TABLE,
    FULL_TABLE_REF,
    PARAM_REDSHIFT_URL,
    PARAM_REDSHIFT_USER,
    PARAM_REDSHIFT_PASSWORD,
    PARAM_REDSHIFT_TMP_DIR,
    PREACTIONS_DDL,
    POSTACTIONS_DDL,
    PARTITION_HELPER_COLUMNS,
    REDSHIFT_JDBC_DRIVER,
    PARAM_REDSHIFT_S3_ROLE_ARN,
)

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

redshift_url      = args[PARAM_REDSHIFT_URL]
redshift_user     = args[PARAM_REDSHIFT_USER]
redshift_password = args[PARAM_REDSHIFT_PASSWORD]
redshift_tmp_dir  = args[PARAM_REDSHIFT_TMP_DIR]
redshift_s3_role_arn = args[PARAM_REDSHIFT_S3_ROLE_ARN] 
# ─────────────────────────────────────────────────────────────────
# Pipeline — 5 steps
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Step 1 — Read processed Parquet from Glue Data Catalog
    dyf = read_catalog_table(
        glue_context = glueContext,
        database     = SOURCE_CATALOG_DATABASE,
        table_name   = SOURCE_CATALOG_TABLE,
    )

    source_row_count = dyf.count()
    logger.info(f"Source row count (Parquet): {source_row_count:,}")

    # Step 2 — Drop partition helper columns (partition_year, partition_month)
    dyf = drop_partition_helper_columns(
        glue_context    = glueContext,
        dyf             = dyf,
        columns_to_drop = PARTITION_HELPER_COLUMNS,
    )

    # Step 3 — Write to Redshift via direct JDBC COPY
    # No Glue connection object used — writers.py connects directly
    # using the JDBC URL injected from Glue job parameters.
    write_to_redshift(
        glue_context      = glueContext,
        dyf               = dyf,
        full_table_ref    = FULL_TABLE_REF,
        preactions_ddl    = PREACTIONS_DDL,
        postactions_ddl   = POSTACTIONS_DDL,
        redshift_url      = redshift_url,
        redshift_user     = redshift_user,
        redshift_password = redshift_password,
        redshift_tmp_dir  = redshift_tmp_dir,
        redshift_s3_role_arn = redshift_s3_role_arn,
    )

    # Step 4 — Post-load validation
    validate_redshift_row_count(
        spark             = spark,
        full_table_ref    = FULL_TABLE_REF,
        expected_count    = source_row_count,
        redshift_url      = redshift_url,
        redshift_user     = redshift_user,
        redshift_password = redshift_password,
        jdbc_driver       = REDSHIFT_JDBC_DRIVER,
    )

    # Step 5 — Commit job bookmark
    job.commit()
    logger.info("Job committed ✓")
