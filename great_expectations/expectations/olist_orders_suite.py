"""
olist_orders_suite.py — Expectation configs for olist_orders

Single responsibility: define what "good data" looks like for this table.
Returns a list of plain dicts — no GX imports, no context, no I/O.

checkpoint.py owns all GX wiring. This file only answers:
    "What expectations apply to olist_orders?"
"""


def get_expectation_configs() -> list[dict]:
    """
    Return expectation configs for the olist_orders processed table.

    Expectations:
        - Row count > 90,000   (full dataset has ~99K orders)
        - order_id not null
        - order_id unique       (primary key)
        - order_status in known set
        - order_purchase_timestamp not null

    Returns:
        List of dicts with keys "expectation_type" and "kwargs".
    """
    return [
        # ── Volume check ──────────────────────────────────────────
        {
            "expectation_type": "expect_table_row_count_to_be_between",
            "kwargs": {
                "min_value": 90_000,
                "max_value": None,   # no upper bound — allows dataset growth
            },
        },

        # ── Primary key: not null ─────────────────────────────────
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "order_id"},
        },

        # ── Primary key: unique ───────────────────────────────────
        {
            "expectation_type": "expect_column_values_to_be_unique",
            "kwargs": {"column": "order_id"},
        },

        # ── order_status: known values only ───────────────────────
        # Source: Olist data dictionary. Any value outside this set
        # indicates a new status category or upstream data corruption.
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {
                "column": "order_status",
                "value_set": [
                    "delivered",
                    "shipped",
                    "canceled",
                    "unavailable",
                    "invoiced",
                    "processing",
                    "approved",
                    "created",
                ],
            },
        },

        # ── order_purchase_timestamp: not null ────────────────────
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "order_purchase_timestamp"},
        },
    ]
