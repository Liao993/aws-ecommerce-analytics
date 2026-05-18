# ─────────────────────────────────────────────────────────────────
# csv_to_parquet_config.py
# Config for the CSV → Parquet Glue ETL job.
# All environment-specific values live here — main.py never has
# hardcoded strings.
# ─────────────────────────────────────────────────────────────────

# Glue Data Catalog database where the Crawler registered the raw CSVs
SOURCE_DATABASE = "olist_dev_raw"

# S3 destination root — all processed Parquet lands under this prefix
TARGET_S3_PREFIX = "s3://olist-ecommerce-tara888/dev/processed"

# Tables that have a natural date column worth partitioning on.
# Partitioned tables get  year=YYYY/month=MM  folder structure so
# Athena and downstream Glue jobs can skip irrelevant months at query time.
# Dimension tables (sellers, products, etc.) are small and written flat.
PARTITIONED_TABLES: dict[str, str] = {
    "olist_orders_dataset_csv":        "order_purchase_timestamp",
    "olist_order_reviews_dataset_csv": "review_creation_date",
}

# All 9 source tables as catalogued by the Glue Crawler.
# Order here determines processing order — transactional tables first
# so dimension tables are available for any downstream validation.
ALL_TABLES: list[str] = [
    "olist_orders_dataset_csv",
    "olist_customers_dataset_csv",
    "olist_order_items_dataset_csv",
    "olist_order_payments_dataset_csv",
    "olist_order_reviews_dataset_csv",
    "olist_products_dataset_csv",
    "olist_sellers_dataset_csv",
    "olist_geolocation_dataset_csv",
    "product_category_name_translation_csv",
]
