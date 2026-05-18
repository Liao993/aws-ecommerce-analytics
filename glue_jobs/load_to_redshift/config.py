# ─────────────────────────────────────────────────────────────────
# config.py — load_to_redshift job
#
# Non-sensitive config committed to Git.
# Credentials (REDSHIFT_URL, REDSHIFT_USER, REDSHIFT_PASSWORD) are
# never stored here — they are injected at Glue job runtime via
# job parameters defined in main.tf.
# ─────────────────────────────────────────────────────────────────

# ── Source ────────────────────────────────────────────────────────
# Glue Data Catalog database and table written by csv_to_parquet.
SOURCE_CATALOG_DATABASE = "olist_dev_processed"
SOURCE_CATALOG_TABLE    = "olist_orders_dataset_csv_processed"

# ── Redshift target ───────────────────────────────────────────────
TARGET_SCHEMA  = "dev_raw"
TARGET_TABLE   = "olist_orders"
FULL_TABLE_REF = f"{TARGET_SCHEMA}.{TARGET_TABLE}"

# ── Runtime parameter keys ────────────────────────────────────────
# These match the --KEY names in the Glue job default_arguments.
# main.py passes these to getResolvedOptions() to pull injected values.
PARAM_REDSHIFT_URL      = "REDSHIFT_URL"
PARAM_REDSHIFT_USER     = "REDSHIFT_USER"
PARAM_REDSHIFT_PASSWORD = "REDSHIFT_PASSWORD"
PARAM_REDSHIFT_TMP_DIR  = "REDSHIFT_TMP_DIR"
PARAM_REDSHIFT_S3_ROLE_ARN = "REDSHIFT_S3_ROLE_ARN"

# ── DDL ───────────────────────────────────────────────────────────
# PREACTIONS: runs before the COPY command.
# Creates schema + table if they don't exist. Safe to re-run.
PREACTIONS_DDL = f"""
CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};

DROP TABLE IF EXISTS {TARGET_SCHEMA}.{TARGET_TABLE};

CREATE TABLE {TARGET_SCHEMA}.{TARGET_TABLE} (
    order_id                          VARCHAR(64)  NOT NULL,
    customer_id                       VARCHAR(64),
    order_status                      VARCHAR(32),
    order_purchase_timestamp          TIMESTAMP,
    order_approved_at                 TIMESTAMP,
    order_delivered_carrier_date      TIMESTAMP,
    order_delivered_customer_date     TIMESTAMP,
    order_estimated_delivery_date     TIMESTAMP
)
DISTSTYLE AUTO
SORTKEY (order_purchase_timestamp);
"""

POSTACTIONS_DDL = ""    # ← empty, DROP TABLE in preactions handles cleanup

# POSTACTIONS: runs after new data is fully staged in S3 tmp,
# before the COPY commits to Redshift.
# TRUNCATE removes the previous full load atomically.
POSTACTIONS_DDL = f"TRUNCATE TABLE {TARGET_SCHEMA}.{TARGET_TABLE};"

# ── Column cleanup ────────────────────────────────────────────────
# Partition routing columns added by csv_to_parquet for Athena pruning.
# Not business columns — must be dropped before Redshift load.
PARTITION_HELPER_COLUMNS = ["partition_year", "partition_month"]

# ── JDBC ──────────────────────────────────────────────────────────
REDSHIFT_JDBC_DRIVER = "com.amazon.redshift.jdbc42.Driver"
