"""
olist_order_items_suite.py — Expectation configs for olist_order_items

Single responsibility: define what "good data" looks like for this table.
Returns a list of plain dicts — no GX imports, no context, no I/O.
"""


def get_expectation_configs() -> list[dict]:
    """
    Return expectation configs for the olist_order_items processed table.

    Expectations:
        - order_id not null         (foreign key — must link to an order)
        - product_id not null       (foreign key — must link to a product)
        - seller_id not null        (foreign key — must link to a seller)
        - price > 0                 (items must have a positive price)
        - freight_value >= 0        (freight can be 0 for free shipping promos)

    Returns:
        List of dicts with keys "expectation_type" and "kwargs".
    """
    return [
        # ── Foreign keys: not null ────────────────────────────────
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "order_id"},
        },
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "product_id"},
        },
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "seller_id"},
        },

        # ── price: strictly positive ──────────────────────────────
        # A price of 0 would indicate a data pipeline bug — free items
        # in Olist are represented differently, not as zero-price line items.
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {
                "column":           "price",
                "min_value":        0,
                "strict_min":       True,   # price > 0, not >= 0
                "max_value":        None,
            },
        },

        # ── freight_value: non-negative ───────────────────────────
        # 0 is valid (free shipping promotions exist in the dataset).
        # Negative freight would be a data error.
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {
                "column":     "freight_value",
                "min_value":  0,
                "strict_min": False,  # freight_value >= 0
                "max_value":  None,
            },
        },
    ]
