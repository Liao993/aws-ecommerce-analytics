# ─────────────────────────────────────────────────────────────────
# config.py — load_to_redshift job (Feature 2.1 — all 9 tables)
#
# Non-sensitive config committed to Git.
# Credentials (REDSHIFT_URL, REDSHIFT_USER, REDSHIFT_PASSWORD, etc.)
# are never stored here — injected at Glue job runtime via Terraform
# job parameters and read by main.py via getResolvedOptions().
#
# Design decisions:
#   - Plain dicts, no dataclass. Each table entry is a dict with
#     consistent keys — readable without knowing any Python class API.
#   - partition_year / partition_month are NOT declared per table.
#     transformers.py auto-detects them at runtime by checking if the
#     column exists in the DataFrame. These two column names are always
#     the same (added by csv_to_parquet) so auto-detection is safe.
#   - timestamp_columns ARE declared explicitly per table because
#     timestamp column names vary (shipping_limit_date, review_creation_date,
#     order_approved_at) and have no reliable naming pattern to auto-detect.
#     Empty list [] = no casting needed for that table (no-op step).
#   - DDL is declared per table. It runs as Redshift COPY preactions:
#     CREATE SCHEMA IF NOT EXISTS → DROP TABLE IF EXISTS → CREATE TABLE.
#     This means the table is created automatically by the Glue job —
#     no manual DDL step in Query Editor needed.
#   - DISTSTYLE AUTO for all tables. At Olist scale (~100K rows) the
#     Redshift planner outperforms hand-tuned distribution keys.
#   - All tables are full truncate-and-reload. Incremental merge is
#     implemented in dbt (Epic 4), not here.
# ─────────────────────────────────────────────────────────────────


# ── Runtime parameter keys ────────────────────────────────────────
# Key names must match --KEY in Terraform default_arguments exactly.
PARAM_REDSHIFT_URL         = "REDSHIFT_URL"
PARAM_REDSHIFT_USER        = "REDSHIFT_USER"
PARAM_REDSHIFT_PASSWORD    = "REDSHIFT_PASSWORD"
PARAM_REDSHIFT_TMP_DIR     = "REDSHIFT_TMP_DIR"
PARAM_REDSHIFT_S3_ROLE_ARN = "REDSHIFT_S3_ROLE_ARN"

# ── Source catalog database ───────────────────────────────────────
SOURCE_CATALOG_DATABASE = "olist_dev_processed"

# ── Target Redshift schema ────────────────────────────────────────
TARGET_SCHEMA = "dev_raw"

# ── JDBC driver ───────────────────────────────────────────────────
REDSHIFT_JDBC_DRIVER = "com.amazon.redshift.jdbc42.Driver"

# ── Partition helper columns — auto-detected at runtime ──────────
# transformers.py checks if these exist in the DataFrame and drops
# them if present. Declared here as a single source of truth so the
# column names are never hardcoded in two places.
PARTITION_HELPER_COLUMNS = ["partition_year", "partition_month"]


# ─────────────────────────────────────────────────────────────────
# Table definitions — all 9 Olist tables
# Each entry is a plain dict with these keys:
#   source_catalog_table  str        Glue catalog table in olist_dev_processed
#   target_table          str        Redshift table name in dev_raw schema
#   target_columns        list[str]  Columns to select and load — must match DDL
#   timestamp_columns     list[str]  Columns to cast to TIMESTAMP before COPY
#                                    Empty list = no casting needed
#   ddl                   str        CREATE SCHEMA + DROP TABLE + CREATE TABLE
#                                    Runs as Redshift COPY preactions
# ─────────────────────────────────────────────────────────────────

TABLES = [

    # ── 1. Orders ─────────────────────────────────────────────────
    # Core transactional table. ~99K rows.
    # Partitioned in S3 by order_purchase_timestamp — partition columns
    # auto-detected and dropped by transformers.py at runtime.
    {
        "source_catalog_table": "olist_orders_dataset_csv_processed",
        "target_table":         "olist_orders",
        "target_columns": [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        "timestamp_columns": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_orders CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_orders (
                order_id                        VARCHAR(64)  NOT NULL,
                customer_id                     VARCHAR(64),
                order_status                    VARCHAR(32),
                order_purchase_timestamp        TIMESTAMP,
                order_approved_at               TIMESTAMP,
                order_delivered_carrier_date    TIMESTAMP,
                order_delivered_customer_date   TIMESTAMP,
                order_estimated_delivery_date   TIMESTAMP
            ) DISTSTYLE AUTO SORTKEY (order_purchase_timestamp);
        """,
    },

    # ── 2. Customers ──────────────────────────────────────────────
    # Dimension table. ~99K rows. No timestamps. No S3 partitioning.
    {
        "source_catalog_table": "olist_customers_dataset_csv_processed",
        "target_table":         "olist_customers",
        "target_columns": [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
        "timestamp_columns": [],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_customers CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_customers (
                customer_id              VARCHAR(64) NOT NULL,
                customer_unique_id       VARCHAR(64),
                customer_zip_code_prefix VARCHAR(16),
                customer_city            VARCHAR(128),
                customer_state           VARCHAR(8)
            ) DISTSTYLE AUTO SORTKEY (customer_id);
        """,
    },

    # ── 3. Order Items ────────────────────────────────────────────
    # Transactional. ~112K rows. Composite key: order_id + order_item_id.
    # shipping_limit_date arrives as string from crawler — cast to TIMESTAMP.
    {
        "source_catalog_table": "olist_order_items_dataset_csv_processed",
        "target_table":         "olist_order_items",
        "target_columns": [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
        "timestamp_columns": ["shipping_limit_date"],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_order_items CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_order_items (
                order_id            VARCHAR(64)   NOT NULL,
                order_item_id       INTEGER,
                product_id          VARCHAR(64),
                seller_id           VARCHAR(64),
                shipping_limit_date TIMESTAMP,
                price               DECIMAL(10,2),
                freight_value       DECIMAL(10,2)
            ) DISTSTYLE AUTO SORTKEY (order_id);
        """,
    },

    # ── 4. Order Payments ─────────────────────────────────────────
    # Transactional. ~104K rows. Multiple rows per order (installments).
    # No timestamps. No S3 partitioning.
    {
        "source_catalog_table": "olist_order_payments_dataset_csv_processed",
        "target_table":         "olist_order_payments",
        "target_columns": [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
        "timestamp_columns": [],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_order_payments CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_order_payments (
                order_id             VARCHAR(64) NOT NULL,
                payment_sequential   INTEGER,
                payment_type         VARCHAR(32),
                payment_installments INTEGER,
                payment_value        DECIMAL(10,2)
            ) DISTSTYLE AUTO SORTKEY (order_id);
        """,
    },

    # ── 5. Order Reviews ─────────────────────────────────────────
    # Transactional. ~100K rows.
    # Partitioned in S3 by review_creation_date — auto-detected and dropped.
    # review_answer_timestamp may be null for unanswered reviews.
    {
        "source_catalog_table": "olist_order_reviews_dataset_csv_processed",
        "target_table":         "olist_order_reviews",
        "target_columns": [
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ],
        "timestamp_columns": [
            "review_creation_date",
            "review_answer_timestamp",
        ],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_order_reviews CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_order_reviews (
                review_id               VARCHAR(64)   NOT NULL,
                order_id                VARCHAR(64),
                review_score            INTEGER,
                review_comment_title    VARCHAR(256),
                review_comment_message  VARCHAR(1024),
                review_creation_date    TIMESTAMP,
                review_answer_timestamp TIMESTAMP
            ) DISTSTYLE AUTO SORTKEY (review_creation_date);
        """,
    },

    # ── 6. Products ───────────────────────────────────────────────
    # Dimension table. ~33K rows. No timestamps. No S3 partitioning.
    # Note: column names "lenght" are intentional — matches source CSV typo.
    {
        "source_catalog_table": "olist_products_dataset_csv_processed",
        "target_table":         "olist_products",
        "target_columns": [
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
        "timestamp_columns": [],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_products CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_products (
                product_id                 VARCHAR(64) NOT NULL,
                product_category_name      VARCHAR(128),
                product_name_lenght        INTEGER,
                product_description_lenght INTEGER,
                product_photos_qty         INTEGER,
                product_weight_g           DECIMAL(10,2),
                product_length_cm          DECIMAL(10,2),
                product_height_cm          DECIMAL(10,2),
                product_width_cm           DECIMAL(10,2)
            ) DISTSTYLE AUTO SORTKEY (product_id);
        """,
    },

    # ── 7. Sellers ────────────────────────────────────────────────
    # Dimension table. ~3K rows (smallest table).
    # No timestamps. No S3 partitioning.
    {
        "source_catalog_table": "olist_sellers_dataset_csv_processed",
        "target_table":         "olist_sellers",
        "target_columns": [
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ],
        "timestamp_columns": [],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_sellers CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_sellers (
                seller_id              VARCHAR(64) NOT NULL,
                seller_zip_code_prefix VARCHAR(16),
                seller_city            VARCHAR(128),
                seller_state           VARCHAR(8)
            ) DISTSTYLE AUTO SORTKEY (seller_id);
        """,
    },

    # ── 8. Geolocation ────────────────────────────────────────────
    # Largest table. ~1M rows. No timestamps. No S3 partitioning.
    # Multiple lat/lng rows per zip code prefix — intentionally denormalized.
    # No SORTKEY: queries filter by city or state, not a single key column.
    {
        "source_catalog_table": "olist_geolocation_dataset_csv_processed",
        "target_table":         "olist_geolocation",
        "target_columns": [
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
            "geolocation_city",
            "geolocation_state",
        ],
        "timestamp_columns": [],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.olist_geolocation CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.olist_geolocation (
                geolocation_zip_code_prefix VARCHAR(16),
                geolocation_lat             DECIMAL(18,15),
                geolocation_lng             DECIMAL(18,15),
                geolocation_city            VARCHAR(128),
                geolocation_state           VARCHAR(8)
            ) DISTSTYLE AUTO;
        """,
    },

    # ── 9. Product Category Name Translation ─────────────────────
    # Reference / lookup table. ~70 rows. No timestamps. No partitioning.
    # Maps Portuguese category names → English translations.
    {
        "source_catalog_table": "product_category_name_translation_csv_processed",
        "target_table":         "product_category_name_translation",
        "target_columns": [
            "product_category_name",
            "product_category_name_english",
        ],
        "timestamp_columns": [],
        "ddl": f"""
            CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};
            DROP TABLE IF EXISTS {TARGET_SCHEMA}.product_category_name_translation CASCADE;
            CREATE TABLE {TARGET_SCHEMA}.product_category_name_translation (
                product_category_name         VARCHAR(128) NOT NULL,
                product_category_name_english VARCHAR(128)
            ) DISTSTYLE AUTO SORTKEY (product_category_name);
        """,
    },
]


# ── Helper: full Redshift table reference ─────────────────────────
def full_table_ref(table: dict) -> str:
    """Return schema-qualified table name, e.g. 'dev_raw.olist_orders'."""
    return f"{TARGET_SCHEMA}.{table['target_table']}"