# ─────────────────────────────────────────────────────────────────
# config.py — great_expectations
#
# Non-sensitive constants only. No credentials here — those are
# injected at runtime from .env via python-dotenv in gx_runner.py.
# ─────────────────────────────────────────────────────────────────

# ── S3 ────────────────────────────────────────────────────────────
S3_BUCKET          = "olist-ecommerce-tara888"
S3_PROCESSED_ROOT  = "dev/processed"
S3_DOCS_PREFIX     = "dev/analytics/gx-docs"
S3_FAILURES_PREFIX = "dev/analytics/gx-failures"

# ── AWS ───────────────────────────────────────────────────────────
AWS_REGION_DEFAULT = "ca-central-1"

# ── Suite registry ────────────────────────────────────────────────
# Maps CLI --table argument → Python module path for that table's suite.
# To add a new table: create the suite file and add one line here.
SUITE_REGISTRY: dict[str, str] = {
    "olist_orders":        "expectations.olist_orders_suite",
    "olist_order_reviews": "expectations.olist_order_reviews_suite",
    "olist_order_items":   "expectations.olist_order_items_suite",
}
