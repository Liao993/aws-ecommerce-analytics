import logging
# pyrefly: ignore [missing-import]
from awsglue.context import GlueContext
# pyrefly: ignore [missing-import]
from awsglue.dynamicframe import DynamicFrame

logger = logging.getLogger(__name__)


def read_catalog_table(
    glue_context: GlueContext,
    database: str,
    table_name: str,
) -> DynamicFrame:
    """
    Read a table from the Glue Data Catalog as a DynamicFrame.

    Used by both csv_to_parquet (reads raw CSV catalog tables) and
    load_to_redshift (reads processed Parquet catalog tables).

    push_down_predicate is omitted — this is a full historical load
    of the static Olist dataset. For incremental jobs, add a predicate
    like "partition_year='2018' and partition_month='01'" here.

    Args:
        glue_context: Active GlueContext from the job bootstrap.
        database:     Glue Data Catalog database name.
        table_name:   Catalog table name within that database.

    Returns:
        DynamicFrame with all rows from the catalog table.

    Raises:
        RuntimeError: If the table returns zero rows, signalling a
                      crawler failure or missing source data upstream.
    """
    logger.info(f"Reading catalog table: {database}.{table_name}")

    dyf = glue_context.create_dynamic_frame.from_catalog(
        database           = database,
        table_name         = table_name,
        transformation_ctx = f"read_{table_name}",
    )

    row_count = dyf.count()
    logger.info(f"{table_name}: {row_count:,} rows read from catalog")

    if row_count == 0:
        raise RuntimeError(
            f"Zero rows returned from {database}.{table_name}. "
            "Verify the Glue Crawler ran successfully and the source data exists in S3."
        )

    return dyf
