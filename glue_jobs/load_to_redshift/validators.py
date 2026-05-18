import logging
from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


def validate_redshift_row_count(
    spark: SparkSession,
    full_table_ref: str,
    expected_count: int,
    redshift_url: str,
    redshift_user: str,
    redshift_password: str,
    jdbc_driver: str,
) -> None:
    """
    Query Redshift directly after load and confirm row count matches source.

    Why this check is necessary:
        Glue's write_dynamic_frame.from_jdbc_conf can silently succeed
        even when the Redshift COPY command rejected some rows due to
        type mismatches or encoding errors. The job appears green in the
        console but the table has fewer rows than expected.

        This validator catches that silent failure before the DAG moves
        to the dbt step — where a missing 5,000 rows would corrupt every
        downstream model silently.

    How it works:
        Uses a direct Spark JDBC read (not through Glue's catalog) to run
        SELECT COUNT(*) on the target table. This bypasses the Glue layer
        entirely and hits Redshift with a raw SQL query.

    What to do on failure:
        Check Redshift's internal error log table:
            SELECT * FROM stl_load_errors ORDER BY starttime DESC LIMIT 20;
        This shows exactly which rows the COPY rejected and why
        (type mismatch, column overflow, encoding issue, etc.)

    Args:
        spark:             Active SparkSession from the Glue job bootstrap.
        full_table_ref:    Schema-qualified table, e.g. "dev_raw.olist_orders".
        expected_count:    Row count from the source Parquet DynamicFrame.
        redshift_url:      Full JDBC URL for Redshift Serverless.
        redshift_user:     Redshift username.
        redshift_password: Redshift password (injected from Secrets Manager).
        jdbc_driver:       Fully-qualified JDBC driver class name.

    Raises:
        RuntimeError: Actual Redshift count does not match expected count.
    """
    logger.info(
        f"Validating row count for {full_table_ref} "
        f"(expected {expected_count:,})"
    )

    validation_query = f"(SELECT COUNT(*) AS cnt FROM {full_table_ref}) AS validation"

    df_check = (
        spark.read
        .format("jdbc")
        .option("url",      redshift_url)
        .option("dbtable",  validation_query)
        .option("user",     redshift_user)
        .option("password", redshift_password)
        .option("driver",   jdbc_driver)
        .load()
    )

    actual_count = df_check.collect()[0]["cnt"]
    logger.info(f"Redshift row count: {actual_count:,}")

    if actual_count != expected_count:
        raise RuntimeError(
            f"Row count mismatch on {full_table_ref}. "
            f"Source Parquet: {expected_count:,} | Redshift: {actual_count:,}. "
            "Check stl_load_errors in Redshift for COPY rejection details."
        )

    logger.info(f"Validation passed ✓  {actual_count:,} rows confirmed in Redshift")
