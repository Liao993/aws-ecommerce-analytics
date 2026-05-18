import logging
from awsglue.transforms import ResolveChoice, DropNullFields
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)


def resolve_and_clean(
    dyf: DynamicFrame,
    table_name: str,
    glue_context: GlueContext,          # ← add this parameter
) -> DynamicFrame:
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

    df = dyf.toDF()

    # Log schema here — instantly shows col0/col1 if crawler ran without classifier
    logger.info(f"{table_name}: columns after resolve = {df.columns}")

    for col in df.columns:
        for suffix in ("_string", "_long", "_double", "_int", "_boolean"):
            if col.endswith(suffix):
                original = col[: -len(suffix)]
                if original not in df.columns:
                    logger.info(f"{table_name}: renaming '{col}' → '{original}'")
                    df = df.withColumnRenamed(col, original)
                break

    return DynamicFrame.fromDF(df, glue_context, f"resolved_{table_name}")  # ← use param


def add_partition_columns(df, date_col: str):
    logger.info(f"Deriving partition columns from '{date_col}'")

    actual_col = date_col
    if date_col not in df.columns:
        fallback = f"{date_col}_string"
        if fallback in df.columns:
            logger.warning(f"'{date_col}' not found, using '{fallback}' instead")
            actual_col = fallback
        else:
            raise ValueError(
                f"Cannot partition: '{date_col}' missing from DataFrame. "
                f"Available columns: {df.columns}"
            )

    df = df.withColumn(
        "_ts",
        F.coalesce(
            F.to_timestamp(F.col(actual_col), "yyyy-MM-dd HH:mm:ss"),
            F.to_timestamp(F.col(actual_col)),
        ),
    )

    null_count = df.filter(F.col("_ts").isNull()).count()
    if null_count > 0:
        logger.warning(
            f"'{actual_col}': {null_count:,} rows could not be parsed as timestamp"
        )

    df = df.withColumn("partition_year",  F.date_format(F.col("_ts"), "yyyy"))
    df = df.withColumn("partition_month", F.date_format(F.col("_ts"), "MM"))
    df = df.drop("_ts")
    return df