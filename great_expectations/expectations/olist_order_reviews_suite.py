"""
olist_order_reviews_suite.py — Expectation configs for olist_order_reviews

Single responsibility: define what "good data" looks like for this table.
Returns a list of plain dicts — no GX imports, no context, no I/O.
"""


def get_expectation_configs() -> list[dict]:
    """
    Return expectation configs for the olist_order_reviews processed table.

    Expectations:
        - review_id not null
        - review_id unique          (primary key)
        - order_id not null         (foreign key — every review must link to an order)
        - review_score between 1–5  (Olist rating scale)
        - review_creation_date not null

    Returns:
        List of dicts with keys "expectation_type" and "kwargs".
    """
    return [
        # ── Primary key: not null ─────────────────────────────────
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "review_id"},
        },

        # -── Primary key: 95% unique ─────────────────────────────
        {
            "expectation_type": "expect_column_proportion_of_unique_values_to_be_between",
            "kwargs": {
                "column": "review_id",
                "min_value": 0.90,
                "max_value": 1.0,
            },
        },
        # ── Foreign key: not null ─────────────────────────────────
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "order_id"},
        },
    

        # ── review_score: 1–5 only ────────────────────────────────
        # Values outside this range are impossible in Olist's system
        # and indicate upstream corruption or a schema change.
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {
                "column":    "review_score",
                "min_value": 1,
                "max_value": 5,
            },
        },

        # ── review_creation_date: not null ────────────────────────
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "review_creation_date"},
        },
    ]
