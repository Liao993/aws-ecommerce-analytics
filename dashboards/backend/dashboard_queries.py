"""
backend/dashboard_queries.py — Cached query functions for the core dashboard

Single responsibility: define the SQL for each of the 5 core dashboard tabs
and wrap each in @st.cache_data(ttl=3600).

All queries hit dev_marts schema (pre-materialized dbt mart tables) —
never dev_staging or dev_intermediate. Marts are the only layer the
readonly Redshift role and this dashboard should touch.
"""

import streamlit as st # type: ignore
import pandas as pd # type: ignore

from backend.redshift_connection import run_query


@st.cache_data(ttl=3600)
def load_seller_performance() -> pd.DataFrame:
    """Seller-grain metrics: revenue/review quartiles, on-time rate, delay days."""
    return run_query("""
        SELECT seller_id, seller_state, total_revenue, avg_review_score,
               on_time_pct, order_count, revenue_quartile, review_quartile,
               review_score_bucket, avg_delay_days
        FROM dev_marts.mart_seller_performance
    """)


@st.cache_data(ttl=3600)
def load_delivery_analysis() -> pd.DataFrame:
    """Top 15 worst origin-destination delivery corridors by avg delay."""
    return run_query("""
        SELECT corridor, origin_state, destination_state,
               order_count, avg_delay_days, late_pct, delay_rank
        FROM dev_marts.mart_delivery_analysis
        ORDER BY delay_rank ASC
        LIMIT 15
    """)


@st.cache_data(ttl=3600)
def load_cohort_retention() -> pd.DataFrame:
    """Cohort-month retention rates at 30/60/90 days, filtered to cohorts >= 50 customers."""
    return run_query("""
        SELECT cohort_month,
               COUNT(*) AS cohort_size,
               ROUND(AVG(repeat_within_30d) * 100, 1) AS retention_30d,
               ROUND(AVG(repeat_within_60d) * 100, 1) AS retention_60d,
               ROUND(AVG(repeat_within_90d) * 100, 1) AS retention_90d
        FROM dev_marts.mart_customer_cohorts
        GROUP BY cohort_month
        HAVING COUNT(*) >= 50
        ORDER BY cohort_month ASC
    """)


@st.cache_data(ttl=3600)
def load_payment_behavior() -> pd.DataFrame:
    """Installment-bucket grain: AOV and cancellation rate by installment count."""
    return run_query("""
        SELECT dimension_value, order_count, avg_order_value,
               cancellation_rate_pct, avg_review_score
        FROM dev_marts.mart_payment_behavior
        WHERE dimension_type = 'installment_bucket'
        ORDER BY
            CASE dimension_value
                WHEN '1 (cash/single)' THEN 1
                WHEN '2-3'             THEN 2
                WHEN '4-6'             THEN 3
                WHEN '7-12'            THEN 4
                WHEN '13+'             THEN 5
            END
    """)


@st.cache_data(ttl=3600)
def load_rfm_segmentation() -> pd.DataFrame:
    """Customer-grain RFM scores and segment labels."""
    return run_query("""
        SELECT customer_unique_id, r_score, f_score, m_score,
               segment, total_spend, total_orders, days_since_last_order
        FROM dev_marts.mart_rfm_segmentation
    """)
