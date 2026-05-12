
import logging
# pyrefly: ignore [missing-import]
from awsglue.transforms import ResolveChoice, DropNullFields
# pyrefly: ignore [missing-import]
from awsglue.dynamicframe import DynamicFrame
# pyrefly: ignore [missing-import]
from pyspark.sql import functions as F


logger = logging.getLogger(__name__)
# ─────────────────────────────────────────────────────────────────
# Parquet writer — used by csv_to_parquet.py
# ─────────────────────────────────────────────────────────────────
 
def add_partition_columns(df, date_col: str):
    """
    Derive partition_year and partition_month string columns from a
    raw timestamp column.
 
    Keeping partition columns as zero-padded strings means Athena reads
    the path  year=2018/month=01  and prunes correctly without needing
    a manual MSCK REPAIR TABLE step after each write.
 
    Args:
        df:       Spark DataFrame containing the raw date column.
        date_col: Name of the string column holding the timestamp value.
 
    Returns:
        DataFrame with partition_year and partition_month columns appended.
    """
    logger.info(f"Deriving partition columns from '{date_col}'")
    df = df.withColumn(
        "_ts",
        F.to_timestamp(F.col(date_col), "yyyy-MM-dd HH:mm:ss"),
    )
    df = df.withColumn("partition_year",  F.date_format(F.col("_ts"), "yyyy"))
    df = df.withColumn("partition_month", F.date_format(F.col("_ts"), "MM"))
    df = df.drop("_ts")
    return df
 
 
def resolve_and_clean(dyf: DynamicFrame, table_name: str) -> DynamicFrame:
    """
    Resolve Glue ChoiceType columns and drop null-only fields.
 
    Glue marks columns whose type is ambiguous across CSV rows as
    ChoiceType. make_cols resolves them to a single consistent type
    so the Parquet writer doesn't fail on schema conflicts from
    inconsistent CSV formatting.
 
    Args:
        dyf:        Raw DynamicFrame from the catalog read.
        table_name: Used as a suffix for transformation context keys.
 
    Returns:
        Cleaned DynamicFrame ready for partitioning or writing.
    """
    logger.info(f"{table_name}: resolving ChoiceType columns")
    dyf = ResolveChoice.apply(
        frame              = dyf,
        choice             = "make_cols",
        transformation_ctx = f"resolve_{table_name}",
    )
    dyf = DropNullFields.apply(
        frame              = dyf,
        transformation_ctx = f"dropnulls_{table_name}",
    )
    return dyf