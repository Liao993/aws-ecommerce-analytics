"""
services/transforms.py — DataFrame transformation utilities

Single responsibility: reshape, clean, and enrich DataFrames returned by
the backend query layer before they reach chart components.

No Streamlit calls, no chart library calls — pure pandas only. This
makes every function here unit-testable without a Streamlit context
and keeps the chart components focused on rendering, not data wrangling.
"""

import pandas as pd  # type: ignore


# ── Seller Performance ────────────────────────────────────────────

def pivot_seller_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot seller_performance to a revenue_quartile × review_quartile matrix
    of average on_time_pct values. Used by the Tab 1 heatmap.

    Args:
        df: Output of load_seller_performance().
            Must contain revenue_quartile, review_quartile, on_time_pct columns.

    Returns:
        Wide DataFrame indexed by revenue_quartile (desc), columns = review_quartile.
    """
    pivot = (
        df.groupby(["revenue_quartile", "review_quartile"])
        .agg(avg_on_time_pct=("on_time_pct", "mean"))
        .reset_index()
    )
    return pivot.pivot(
        index="revenue_quartile",
        columns="review_quartile",
        values="avg_on_time_pct",
    ).sort_index(ascending=False)


# ── Delivery Analysis ─────────────────────────────────────────────

def sort_corridors_by_delay(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort corridors ascending by avg_delay_days (for horizontal bar charts
    where bottom entry = worst performer after Plotly reverses the axis).

    Args:
        df: Output of load_delivery_analysis().

    Returns:
        DataFrame sorted ascending on avg_delay_days.
    """
    return df.sort_values("avg_delay_days", ascending=True).reset_index(drop=True)


# ── Cohort Retention ──────────────────────────────────────────────

def format_cohort_month(df: pd.DataFrame, col: str = "cohort_month") -> pd.DataFrame:
    """
    Cast a cohort_month column to YYYY-MM string for display in charts.

    Args:
        df: DataFrame containing a datetime-parseable cohort_month column.
        col: Column name (default 'cohort_month').

    Returns:
        DataFrame with col converted to 'YYYY-MM' string.
    """
    df = df.copy()
    df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m")
    return df


def melt_retention_for_heatmap(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Transform the wide cohort retention DataFrame into both:
      - a melted long-format DataFrame for the Plotly imshow heatmap
      - a pivoted wide DataFrame (cohort_month × window) ready for imshow

    Args:
        df: Output of load_cohort_retention().
            Must have columns cohort_month, retention_30d, retention_60d,
            retention_90d (or the _pct variants, which are normalised here).

    Returns:
        Tuple of (melted_df, heatmap_pivot_df).
    """
    df = df.copy()

    # Normalise column names — accept either retention_30d or retention_30d_pct
    rename_map = {
        "retention_30d_pct": "retention_30d",
        "retention_60d_pct": "retention_60d",
        "retention_90d_pct": "retention_90d",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    id_cols = [c for c in ["cohort_month", "cohort_size"] if c in df.columns]
    melted = df.melt(
        id_vars=id_cols,
        value_vars=["retention_30d", "retention_60d", "retention_90d"],
        var_name="window",
        value_name="retention_pct",
    )
    melted["window"] = melted["window"].map({
        "retention_30d": "30 Days",
        "retention_60d": "60 Days",
        "retention_90d": "90 Days",
    })

    pivot = melted.pivot(
        index="cohort_month",
        columns="window",
        values="retention_pct",
    )[["30 Days", "60 Days", "90 Days"]]

    return melted, pivot


# ── RFM Segmentation ─────────────────────────────────────────────

def cast_rfm_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast RFM score columns to int and total_spend to float. Redshift can
    return these as Decimal objects which confuse Altair's type inference.

    Args:
        df: Output of load_rfm_segmentation().

    Returns:
        DataFrame with corrected dtypes.
    """
    df = df.copy()
    for col in ["r_score", "f_score", "m_score", "total_orders", "days_since_last_order"]:
        if col in df.columns:
            df[col] = df[col].astype(int)
    if "total_spend" in df.columns:
        df["total_spend"] = df["total_spend"].astype(float)
    return df


def sample_rfm_for_chart(df: pd.DataFrame, max_rows: int = 5000) -> pd.DataFrame:
    """
    Sample the RFM DataFrame down to max_rows for the Altair scatter chart.
    At full size (~95K rows) the chart renders slowly in-browser.

    Args:
        df: Full RFM DataFrame.
        max_rows: Cap on plotted points (default 5000).

    Returns:
        Sampled DataFrame.
    """
    return df.sample(min(max_rows, len(df)), random_state=42)