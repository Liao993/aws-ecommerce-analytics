

import logging
from urllib.parse import urlparse

import boto3
# pyrefly: ignore [missing-import]
from awsglue.context import GlueContext
# pyrefly: ignore [missing-import]
from awsglue.dynamicframe import DynamicFrame

 
logger = logging.getLogger(__name__)
 
 
def _delete_s3_prefix(s3_uri: str) -> None:
    """
    Remove existing objects under a processed table prefix before rewriting.

    Glue's S3 sink appends by default. Without this cleanup, every DAG run
    adds another copy of the same table and uniqueness checks fail downstream.
    """
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Expected S3 URI, got: {s3_uri}")

    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    deleted = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        for i in range(0, len(objects), 1000):
            batch = objects[i : i + 1000]
            if batch:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": batch})
                deleted += len(batch)

    logger.info(f"Deleted {deleted} existing objects from {s3_uri}")


 
 
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
    _delete_s3_prefix(target_path)

    # Processed tables go into a dedicated catalog database — not the
    # raw source database — so schema conflicts can never occur between
    # raw and processed entries sharing the same namespace.
    processed_database = source_database.replace("_raw", "_processed")
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
        catalogDatabase  = processed_database,
        catalogTableName = f"{table_name}_processed",
    )
    sink.writeFrame(dyf)
    logger.info(f"{table_name}: Parquet write complete ✓")
