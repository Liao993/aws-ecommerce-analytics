

import logging
# pyrefly: ignore [missing-import]
from awsglue.context import GlueContext
# pyrefly: ignore [missing-import]
from awsglue.dynamicframe import DynamicFrame

 
logger = logging.getLogger(__name__)
 
 

 
 
def write_parquet(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    table_name: str,
    target_s3_prefix: str,
    source_database: str,
    partition_keys: list[str],
) -> None:
    """
    Write a DynamicFrame to S3 as Parquet (Snappy compressed) and
    update the Glue Data Catalog so the processed table is queryable
    in Athena immediately — no MSCK REPAIR required.
 
    Args:
        glue_context:     Active GlueContext.
        dyf:              DynamicFrame to write.
        table_name:       Used to build the S3 path and catalog table name.
        target_s3_prefix: Root S3 path, e.g. s3://bucket/dev/processed.
        source_database:  Glue catalog database for the output table entry.
        partition_keys:   ["partition_year","partition_month"] or [] for flat.
    """
    target_path = f"{target_s3_prefix}/{table_name}/"
    logger.info(
        f"Writing {table_name} → {target_path} | "
        f"partitions: {partition_keys or 'none'}"
    )
 
    sink = glue_context.getSink(
        connection_type     = "s3",
        path                = target_path,
        enableUpdateCatalog = True,
        updateBehavior      = "UPDATE_IN_DATABASE",
        partitionKeys       = partition_keys,
        transformation_ctx  = f"write_{table_name}",
    )
    sink.setFormat("glueparquet", compression="snappy")
    sink.setCatalogInfo(
        catalogDatabase  = source_database,
        catalogTableName = f"{table_name}_processed",
    )
    sink.writeFrame(dyf)
    logger.info(f"{table_name}: Parquet write complete ✓")