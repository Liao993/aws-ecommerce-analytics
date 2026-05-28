# ─────────────────────────────────────────────────────────────────
# writers.py — load_to_redshift job
#
# Single responsibility: write a fully-prepared DynamicFrame to
# Redshift via the spark-redshift community connector.
#
# All data transformation (column renaming, dropping, casting,
# projecting) happens in transformers.py before this function runs.
# By the time write_to_redshift() is called, the DynamicFrame
# already contains exactly the right columns in the right types.
# ─────────────────────────────────────────────────────────────────

import logging
# pyrefly: ignore [missing-import]
from awsglue.context import GlueContext
# pyrefly: ignore [missing-import]
from awsglue.dynamicframe import DynamicFrame

logger = logging.getLogger(__name__)


def write_to_redshift(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    full_table_ref: str,
    ddl: str,
    redshift_url: str,
    redshift_user: str,
    redshift_password: str,
    redshift_tmp_dir: str,
    redshift_s3_role_arn: str,
    table_name: str,
) -> None:
    """
    Load a fully-prepared DynamicFrame into Redshift using the
    spark-redshift community connector.

    Why spark-redshift instead of Glue's built-in write_dynamic_frame:
        Glue's DynamicFrame Redshift wrapper can preserve stale ChoiceType
        metadata (e.g. *_string columns) even after DataFrame projection.
        The spark-redshift connector works directly on the Spark DataFrame,
        so the schema it sends to Redshift is exactly what you see in the
        DataFrame — no hidden metadata leaking through.

    How the DDL preactions work:
        The connector runs the preactions string as a JDBC statement against
        Redshift BEFORE issuing the COPY command. The DDL from config.py does:
            1. CREATE SCHEMA IF NOT EXISTS dev_raw
            2. DROP TABLE IF EXISTS dev_raw.<table>    ← full truncate
            3. CREATE TABLE dev_raw.<table> (...)       ← fresh table
        Then the COPY loads the staged Parquet into the new table.
        This is a full truncate-and-reload pattern. Incremental merge
        is implemented in dbt (Epic 4).

    How the COPY staging works:
        The connector stages the DataFrame as Parquet in redshift_tmp_dir
        (s3://olist-ecommerce-tara888/dev/tmp/), then issues a Redshift
        COPY command that reads from that S3 path. Redshift needs the
        redshift_s3_role_arn (olist-redshift-s3-role) to access that S3 path —
        that role is attached to the Redshift namespace in Terraform.

    Args:
        glue_context:        Active GlueContext.
        dyf:                 Fully-prepared DynamicFrame (from transformers.py).
                             Must contain exactly the columns matching the DDL.
        full_table_ref:      Schema-qualified target: "dev_raw.olist_orders".
                             Use config.full_table_ref(table) to build this.
        ddl:                 CREATE SCHEMA + DROP TABLE + CREATE TABLE string.
                             From config table dict["ddl"].
        redshift_url:        Full JDBC URL for Redshift Serverless.
        redshift_user:       Redshift database username (not IAM).
        redshift_password:   Redshift database password (injected at runtime).
        redshift_tmp_dir:    S3 path for COPY staging files.
        redshift_s3_role_arn: IAM role ARN attached to Redshift namespace.
        table_name:          Used for log context only.

    Raises:
        Exception: Any connector / JDBC / Redshift error propagates up to
                   main.py's per-table try/except handler.
    """
    row_count = dyf.count()
    logger.info(f"{table_name}: loading {row_count:,} rows → {full_table_ref}")

    df = dyf.toDF()
    logger.info(f"{table_name}: DataFrame schema sent to Redshift: {df.dtypes}")

    # Collapse multi-line DDL to a single space-separated string.
    # The connector passes preactions as a single JDBC statement — embedded
    # newlines can cause parse errors in some Redshift JDBC driver versions.
    preactions_sql = " ".join(ddl.split())

    (
        df.write
        .format("io.github.spark_redshift_community.spark.redshift")
        .option("url",          redshift_url)
        .option("user",         redshift_user)
        .option("password",     redshift_password)
        .option("dbtable",      full_table_ref)
        .option("tempdir",      redshift_tmp_dir)
        .option("aws_iam_role", redshift_s3_role_arn)
        .option("preactions",   preactions_sql)
        .option("postactions",  "")
        .mode("append")
        .save()
    )

    logger.info(f"{table_name}: Redshift COPY complete → {full_table_ref} ✓")