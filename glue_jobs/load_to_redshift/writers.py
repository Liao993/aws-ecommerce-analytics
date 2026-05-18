import logging
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame

logger = logging.getLogger(__name__)


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
    Load a DynamicFrame into Redshift using write_dynamic_frame.from_options.

    Why from_options instead of getSink:
        getSink for Redshift requires 'location' key internally which maps
        to dbtable — the parameter contract is inconsistent across Glue versions
        and throws 'key not found: location' when path/dbtable are mismatched.

        from_options with connection_type="redshift" has a stable, documented
        parameter contract: url, user, password, dbtable, redshiftTmpDir,
        preactions, postactions — all passed flat in connection_options.
        Uses native Redshift COPY via S3 staging — same bulk performance.
    """
    row_count = dyf.count()
    logger.info(f"Loading {row_count:,} rows → Redshift {full_table_ref}")

    glue_context.write_dynamic_frame.from_options(
        frame           = dyf,
        connection_type = "redshift",
        connection_options = {
            "url"            : redshift_url,
            "user"           : redshift_user,
            "password"       : redshift_password,
            "dbtable"        : full_table_ref,
            "redshiftTmpDir" : redshift_tmp_dir,
            "preactions"     : preactions_ddl,
            "postactions"    : postactions_ddl,
            "aws_iam_role"   : redshift_s3_role_arn,
        },
        transformation_ctx = "write_to_redshift",
    )

    logger.info(f"Redshift COPY complete → {full_table_ref} ✓")