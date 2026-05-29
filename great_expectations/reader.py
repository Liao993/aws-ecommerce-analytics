"""
reader.py — S3 Parquet reader

Single responsibility: read all Parquet files under a processed S3 prefix
into a pandas DataFrame. Nothing else.

Called by gx_runner.py as the first step in the pipeline.
"""

import logging
import os

import pandas as pd # type: ignore

from config import S3_BUCKET, S3_PROCESSED_ROOT

logger = logging.getLogger(__name__)


def read_parquet_from_s3(table_name: str, aws_region: str) -> pd.DataFrame:
    """
    Read all Parquet files under s3://{bucket}/dev/processed/{table_name}/
    into a single pandas DataFrame.

    Uses pyarrow under the hood via pandas read_parquet with the s3:// URI.
    AWS credentials are pulled from environment variables (set by .env via
    python-dotenv in gx_runner.py before this is called).

    Args:
        table_name: Matches the folder name under dev/processed/.
                    e.g. "olist_orders" → s3://.../dev/processed/olist_orders/
        aws_region: AWS region string, e.g. "ca-central-1".

    Returns:
        pandas DataFrame with all rows from the processed Parquet partition.

    Raises:
        RuntimeError: If the DataFrame comes back empty — signals that
                      csv_to_parquet did not write anything to this prefix.
    """
    s3_path = f"s3://{S3_BUCKET}/{S3_PROCESSED_ROOT}/{table_name}_dataset_csv/"
    logger.info(f"Reading Parquet from {s3_path}")

    df = pd.read_parquet(
        s3_path,
        storage_options={
            "key":    os.getenv("AWS_ACCESS_KEY_ID"),
            "secret": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "client_kwargs": {"region_name": aws_region},
        },
    )

    row_count = len(df)
    logger.info(f"Loaded {row_count:,} rows × {len(df.columns)} columns from {table_name}")

    if row_count == 0:
        raise RuntimeError(
            f"Zero rows returned from {s3_path}. "
            "Verify csv_to_parquet Glue job ran and wrote files to this prefix."
        )

    return df
