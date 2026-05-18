import logging
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame

logger = logging.getLogger(__name__)


def read_catalog_table(
    glue_context: GlueContext,
    database: str,
    table_name: str,
) -> DynamicFrame:
    """
    Read a processed Parquet table from the Glue Data Catalog into memory.

    In this job the catalog table being read is olist_orders_dataset_processed —
    the entry that csv_to_parquet/main.py created via getSink(enableUpdateCatalog=True).
    The catalog entry points at dev/processed/olist_orders_dataset/ Parquet files.

    Same two-step mechanism as csv_to_parquet/readers.py:
        Step 1 → catalog lookup: where is the file? what are the columns?
        Step 2 → S3 read: actual Parquet bytes loaded into Spark memory

    Why read Parquet via the catalog instead of raw S3 path:
        The catalog entry already has the correct schema, partition info,
        and S3 location. Reading via catalog means this job stays in sync
        with whatever csv_to_parquet wrote — no hardcoded S3 paths here.

    Args:
        glue_context: Active GlueContext from the job bootstrap.
        database:     Glue catalog database (e.g. "olist_dev_raw").
        table_name:   Processed catalog table (e.g. "olist_orders_dataset_processed").

    Returns:
        DynamicFrame with all Parquet rows loaded into Spark memory.

    Raises:
        RuntimeError: Zero rows — csv_to_parquet likely did not run
                      or the Parquet files are missing from S3.
    """
    logger.info(f"Reading processed Parquet: {database}.{table_name}")

    dyf = glue_context.create_dynamic_frame.from_catalog(
        database           = database,
        table_name         = table_name,
        transformation_ctx = f"read_{table_name}",
    )

    row_count = dyf.count()
    logger.info(f"{table_name}: {row_count:,} rows loaded from Parquet")

    if row_count == 0:
        raise RuntimeError(
            f"Zero rows from {database}.{table_name}. "
            "Verify csv_to_parquet/main.py ran successfully before this job."
        )

    return dyf
