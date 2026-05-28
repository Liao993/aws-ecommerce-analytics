# ─────────────────────────────────────────────────────────────────
# transformers.py — load_to_redshift job
#
# All data transformation steps that prepare a DynamicFrame for
# Redshift COPY. None of these functions touch Redshift — they only
# reshape the in-memory Spark DataFrame.
#
# Function responsibility:
#   normalize_choice_type_columns  — fix Glue ChoiceType column name artifacts
#   drop_partition_helper_columns  — remove S3 routing columns (auto-detected)
#   cast_timestamp_columns         — cast string dates to TimestampType
#   select_target_columns          — project to exact Redshift target columns
#
# Called in order by process_table() in main.py.
# ─────────────────────────────────────────────────────────────────

import logging
# pyrefly: ignore [missing-import]
from awsglue.context import GlueContext
# pyrefly: ignore [missing-import]
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)

# Suffixes Glue appends to ambiguous ChoiceType columns.
# e.g. order_approved_at → order_approved_at_string
GLUE_CHOICE_SUFFIXES = ("_string", "_long", "_double", "_int", "_boolean")


def normalize_choice_type_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    table_name: str,
) -> DynamicFrame:
    """
    Rename Glue ResolveChoice-style columns back to their business names.

    When csv_to_parquet runs ResolveChoice with make_cols, columns like
    order_approved_at (a nullable timestamp string) can become
    order_approved_at_string. If the canonical name also exists, the
    suffixed duplicate is dropped instead of renamed.

    This must run before select_target_columns — otherwise the column
    names won't match what config.py declares as target_columns.

    Args:
        glue_context: Active GlueContext (needed for fromDF).
        dyf:          Input DynamicFrame from the Glue catalog read.
        table_name:   Used for log context only.

    Returns:
        DynamicFrame with all ChoiceType suffixes removed.
    """
    df = dyf.toDF()

    for col in df.columns:
        for suffix in GLUE_CHOICE_SUFFIXES:
            if not col.endswith(suffix):
                continue
            canonical = col[: -len(suffix)]
            if canonical in df.columns:
                df = df.drop(col)
                logger.info(f"{table_name}: dropped duplicate ChoiceType column: {col}")
            else:
                df = df.withColumnRenamed(col, canonical)
                logger.info(f"{table_name}: renamed ChoiceType column: {col} → {canonical}")
            break

    logger.info(f"{table_name}: schema after ChoiceType normalization: {df.columns}")
    return DynamicFrame.fromDF(df, glue_context, f"normalized_{table_name}")


def drop_partition_helper_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    partition_helper_columns: list,
    table_name: str,
) -> DynamicFrame:
    """
    Auto-detect and remove S3 partition routing columns before Redshift load.

    csv_to_parquet adds partition_year and partition_month to create the
    year=YYYY/month=MM folder structure in S3 for Athena partition pruning.
    These columns have no business meaning and must not reach Redshift.

    Detection is automatic — the function checks if each column name in
    partition_helper_columns exists in the DataFrame and drops it if found.
    Tables without partitioning (customers, sellers, etc.) simply have no
    matching columns, so this step is a no-op for them. No per-table config
    needed for partition columns because the names are always the same two.

    Args:
        glue_context:             Active GlueContext (needed for fromDF).
        dyf:                      Input DynamicFrame.
        partition_helper_columns: Column names to auto-detect and drop.
                                  Comes from config.PARTITION_HELPER_COLUMNS.
        table_name:               Used for log context only.

    Returns:
        DynamicFrame with partition helper columns removed if they existed.
    """
    df = dyf.toDF()
    dropped = []

    for col in partition_helper_columns:
        if col in df.columns:
            df = df.drop(col)
            dropped.append(col)

    if dropped:
        logger.info(f"{table_name}: auto-dropped partition columns: {dropped}")
    else:
        logger.debug(f"{table_name}: no partition columns found — skipping drop")

    logger.info(f"{table_name}: schema after partition column drop: {df.columns}")
    return DynamicFrame.fromDF(df, glue_context, f"clean_{table_name}")


def cast_timestamp_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    timestamp_columns: list,
    table_name: str,
) -> DynamicFrame:
    """
    Cast timestamp-like string columns to Spark TimestampType.

    The processed Parquet is produced from CSV crawler output, so date/time
    columns arrive as strings. Redshift rejects string values when the target
    DDL column type is TIMESTAMP.

    Timestamp columns are declared explicitly in config.py per table because
    column names vary (shipping_limit_date, review_creation_date, etc.) and
    have no reliable naming pattern for auto-detection.

    When timestamp_columns is [] (dimension tables with no date fields),
    this function returns immediately — no-op. main.py calls this step for
    every table uniformly without any if/else branching.

    Args:
        glue_context:      Active GlueContext (needed for fromDF).
        dyf:               Input DynamicFrame.
        timestamp_columns: Columns to cast. From config table dict.
                           Empty list = no-op.
        table_name:        Used for log context only.

    Returns:
        DynamicFrame with declared timestamp columns cast to TimestampType.
    """
    if not timestamp_columns:
        logger.info(f"{table_name}: no timestamp columns declared — skipping cast step")
        return dyf

    df = dyf.toDF()

    for col in timestamp_columns:
        if col not in df.columns:
            logger.warning(f"{table_name}: timestamp column '{col}' not found — skipping")
            continue

        # Try explicit format first, fall back to Spark's auto-inference.
        # coalesce returns the first non-null result.
        parsed = F.coalesce(
            F.to_timestamp(F.col(col), "yyyy-MM-dd HH:mm:ss"),
            F.to_timestamp(F.col(col)),
        )

        # Count rows where original value is not null but parsed result is null.
        # These are values that couldn't be parsed — worth surfacing as a warning.
        bad_count = df.filter(F.col(col).isNotNull() & parsed.isNull()).count()
        if bad_count > 0:
            logger.warning(
                f"{table_name}: {col}: {bad_count:,} non-null values "
                "could not be parsed as TIMESTAMP"
            )

        df = df.withColumn(col, parsed)
        logger.info(f"{table_name}: cast to TIMESTAMP: {col}")

    logger.info(f"{table_name}: schema after timestamp casts: {df.dtypes}")
    return DynamicFrame.fromDF(df, glue_context, f"typed_{table_name}")


def select_target_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    target_columns: list,
    table_name: str,
) -> DynamicFrame:
    """
    Project the DynamicFrame to exactly the columns declared in config.py.

    This is the final transformation before the Redshift write. It ensures:
      1. Only columns present in the target DDL are passed to the COPY.
      2. Columns are in the same order as the DDL (Redshift COPY is order-sensitive).
      3. Any unexpected extra columns from the catalog read are dropped.
      4. Missing required columns raise ValueError early — before COPY runs —
         so the error message is clear rather than a cryptic Redshift COPY failure.

    Args:
        glue_context:   Active GlueContext (needed for fromDF).
        dyf:            Input DynamicFrame after all prior transformations.
        target_columns: Ordered list from config table dict["target_columns"].
        table_name:     Used for log context and error messages.

    Returns:
        DynamicFrame with exactly target_columns in declared order.

    Raises:
        ValueError: One or more required columns are missing from the DataFrame.
                    Check that csv_to_parquet wrote the expected schema and that
                    normalize_choice_type_columns ran before this step.
    """
    df = dyf.toDF()

    missing = [col for col in target_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"{table_name}: cannot load to Redshift — required columns missing: "
            f"{missing}. Available columns: {list(df.columns)}"
        )

    extra = [col for col in df.columns if col not in target_columns]
    if extra:
        logger.info(f"{table_name}: dropping extra columns not in Redshift target: {extra}")

    df = df.select(*target_columns)
    logger.info(f"{table_name}: final load schema: {df.dtypes}")
    return DynamicFrame.fromDF(df, glue_context, f"target_{table_name}")
