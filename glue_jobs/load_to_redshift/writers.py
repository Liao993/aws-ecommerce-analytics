import logging
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)

GLUE_CHOICE_SUFFIXES = ("_string", "_long", "_double", "_int", "_boolean")


def normalize_choice_type_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
) -> DynamicFrame:
    """
    Rename Glue ResolveChoice-style columns back to their business names.

    The upstream CSV-to-Parquet job can produce columns such as
    order_approved_at_string when Glue infers nullable timestamp strings as
    ChoiceType. Redshift COPY sends all DynamicFrame columns, so those helper
    suffixes must be removed before loading into a fixed target table.
    """
    df = dyf.toDF()

    for col in df.columns:
        for suffix in GLUE_CHOICE_SUFFIXES:
            if not col.endswith(suffix):
                continue

            canonical_col = col[: -len(suffix)]
            if canonical_col in df.columns:
                df = df.drop(col)
                logger.info(
                    f"Dropped duplicate ChoiceType helper column: {col}"
                )
            else:
                df = df.withColumnRenamed(col, canonical_col)
                logger.info(f"Renamed ChoiceType column: {col} -> {canonical_col}")
            break

    logger.info(f"Schema after ChoiceType normalization: {df.columns}")
    return DynamicFrame.fromDF(df, glue_context, "normalized_for_redshift")


def drop_partition_helper_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    columns_to_drop: list[str],
) -> DynamicFrame:
    """
    Remove S3 partition routing columns before loading to Redshift.

    csv_to_parquet added partition_year and partition_month to create
    the year=YYYY/month=MM folder structure in S3 for Athena pruning.
    Those columns have no business meaning and must not reach Redshift.

    DynamicFrame has no native drop() method, so we convert to a Spark
    DataFrame (which has drop()), remove the columns, then convert back.

    Args:
        glue_context:    Active GlueContext (needed for fromDF conversion).
        dyf:             Input DynamicFrame still carrying partition columns.
        columns_to_drop: Column names to remove (from config.py).

    Returns:
        DynamicFrame without partition helper columns.
    """
    df = dyf.toDF()

    for col in columns_to_drop:
        if col in df.columns:
            df = df.drop(col)
            logger.info(f"Dropped partition column: {col}")
        else:
            logger.warning(f"Column '{col}' not found — skipping drop")

    logger.info(f"Schema after column drop: {df.columns}")
    return DynamicFrame.fromDF(df, glue_context, "clean_for_redshift")


def cast_timestamp_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    timestamp_columns: list[str],
) -> DynamicFrame:
    """
    Cast timestamp-like strings to Spark timestamps before Redshift COPY.

    The processed Parquet is produced from CSV crawler output, so date/time
    columns commonly arrive as strings. Redshift rejects those when the target
    table column is TIMESTAMP.
    """
    df = dyf.toDF()

    for col in timestamp_columns:
        if col not in df.columns:
            logger.warning(f"Timestamp column '{col}' not found — skipping cast")
            continue

        parsed_col = F.coalesce(
            F.to_timestamp(F.col(col), "yyyy-MM-dd HH:mm:ss"),
            F.to_timestamp(F.col(col)),
        )
        bad_count = df.filter(F.col(col).isNotNull() & parsed_col.isNull()).count()
        if bad_count > 0:
            logger.warning(
                f"{col}: {bad_count:,} non-null values could not be parsed as TIMESTAMP"
            )

        df = df.withColumn(col, parsed_col)
        logger.info(f"Casted timestamp column: {col}")

    logger.info(f"Schema after timestamp casts: {df.dtypes}")
    return DynamicFrame.fromDF(df, glue_context, "typed_for_redshift")


def select_target_columns(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    target_columns: list[str],
) -> DynamicFrame:
    """
    Keep only the columns declared in the Redshift target table.
    """
    df = dyf.toDF()
    missing_columns = [col for col in target_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(
            "Cannot load to Redshift because required columns are missing: "
            f"{missing_columns}. Available columns: {df.columns}"
        )

    extra_columns = [col for col in df.columns if col not in target_columns]
    if extra_columns:
        logger.info(f"Dropping columns not present in Redshift target: {extra_columns}")

    df = df.select(*target_columns)
    logger.info(f"Final Redshift load schema: {df.dtypes}")
    return DynamicFrame.fromDF(df, glue_context, "target_columns_for_redshift")


def write_to_redshift(
    glue_context: GlueContext,
    dyf: DynamicFrame,
    full_table_ref: str,
    preactions_ddl: str,
    postactions_ddl: str,
    redshift_url: str,
    redshift_user: str,
    redshift_password: str,
    redshift_tmp_dir: str,
    redshift_s3_role_arn: str,
) -> None:
    """
    Load a DynamicFrame into Redshift using the Spark Redshift connector.

    This avoids Glue's DynamicFrame Redshift wrapper preserving stale
    ChoiceType metadata such as *_string columns after DataFrame projection.
    """
    row_count = dyf.count()
    logger.info(f"Loading {row_count:,} rows → Redshift {full_table_ref}")

    df = dyf.toDF()
    logger.info(f"DataFrame schema sent to Redshift: {df.dtypes}")

    (
        df.write
        .format("io.github.spark_redshift_community.spark.redshift")
        .option("url", redshift_url)
        .option("user", redshift_user)
        .option("password", redshift_password)
        .option("dbtable", full_table_ref)
        .option("tempdir", redshift_tmp_dir)
        .option("aws_iam_role", redshift_s3_role_arn)
        .option("preactions", " ".join(preactions_ddl.split()))
        .option("postactions", " ".join(postactions_ddl.split()))
        .mode("append")
        .save()
    )

    logger.info(f"Redshift COPY complete → {full_table_ref} ✓")
