"""
components/charts.py — Chart-building functions

Single responsibility: accept a clean, pre-transformed DataFrame and return
a Plotly Figure or Altair Chart. No SQL, no pandas reshaping, no Streamlit
calls — only chart configuration.

Callers (page modules) are responsible for:
  - Calling the right backend query function
  - Passing the result through services/transforms.py if reshaping is needed
  - Calling st.plotly_chart() / st.altair_chart() on the returned figure

Every function signature documents its required DataFrame columns so callers
know what shape they need to produce before calling here.
"""

from __future__ import annotations

import plotly.express as px  # type: ignore
import plotly.graph_objects as go  # type: ignore
import altair as alt  # type: ignore
import pandas as pd  # type: ignore


# ── Seller Performance ────────────────────────────────────────────

def seller_heatmap(pivot_df: pd.DataFrame) -> go.Figure:
    """
    NTILE heatmap: on-time % by revenue quartile × review quartile.

    Args:
        pivot_df: Wide DataFrame. Index = revenue_quartile (desc),
                  columns = review_quartile, values = avg on_time_pct.
                  Produced by services.transforms.pivot_seller_heatmap().

    Returns:
        Plotly Figure (px.imshow).
    """
    fig = px.imshow(
        pivot_df,
        labels=dict(
            x="Review Quartile (1 = worst rated, 4 = best)",
            y="Revenue Quartile (1 = lowest revenue, 4 = highest)",
            color="Avg On-Time %",
        ),
        color_continuous_scale="RdYlGn",
        title="Seller NTILE Matrix — On-Time Rate by Revenue × Review Quartile",
        text_auto=".1f",
    )
    fig.update_layout(height=450)
    return fig


# ── Delivery Analysis ─────────────────────────────────────────────

def delivery_corridor_bar(df: pd.DataFrame) -> go.Figure:
    """
    Horizontal bar chart: top 15 corridors by average delay days.

    Args:
        df: Must contain corridor, avg_delay_days, late_pct, order_count.
            Should be sorted ascending on avg_delay_days (worst corridor
            ends up at top of chart after Plotly reverses the y-axis).
            Produced by sort_corridors_by_delay() in services/transforms.py.

    Returns:
        Plotly Figure (px.bar horizontal).
    """
    fig = px.bar(
        df,
        x="avg_delay_days",
        y="corridor",
        orientation="h",
        color="late_pct",
        color_continuous_scale="Reds",
        labels={
            "avg_delay_days": "Avg Delay Days",
            "corridor": "Corridor (Origin → Destination)",
            "late_pct": "% Late",
        },
        title="Top 15 Corridors by Average Delivery Delay",
        hover_data=["order_count", "late_pct"],
        text="avg_delay_days",
    )
    fig.update_traces(texttemplate="%{text:.1f}d", textposition="outside")
    fig.update_layout(height=550, coloraxis_showscale=True)
    return fig


# ── Customer Cohort Retention ─────────────────────────────────────

def cohort_heatmap(heatmap_pivot: pd.DataFrame) -> go.Figure:
    """
    Heatmap: retention % by cohort month × window (30/60/90 days).

    Args:
        heatmap_pivot: Wide DataFrame. Index = cohort_month (YYYY-MM string),
                       columns = ['30 Days', '60 Days', '90 Days'],
                       values = retention_pct.
                       Produced by services.transforms.melt_retention_for_heatmap().

    Returns:
        Plotly Figure (px.imshow).
    """
    fig = px.imshow(
        heatmap_pivot,
        labels=dict(x="Retention Window", y="Cohort Month", color="Retention %"),
        color_continuous_scale="Blues",
        title="Cohort Retention Heatmap — % Repeat Purchase by Acquisition Month",
        text_auto=".1f",
        aspect="auto",
    )
    fig.update_layout(height=500)
    return fig


# ── Payment Behavior ──────────────────────────────────────────────

def payment_dual_axis(df: pd.DataFrame, x_col: str = "dimension_value") -> go.Figure:
    """
    Dual-axis chart: bar (AOV) + line (cancellation rate %).

    Args:
        df: Must contain columns for x_col, avg_order_value,
            cancellation_rate_pct. Rows should be in logical display order.

    Returns:
        Plotly Figure with two y-axes.
    """
    fig = px.bar(
        df,
        x=x_col,
        y="avg_order_value",
        color_discrete_sequence=["#4C72B0"],
        labels={
            x_col: "Bucket",
            "avg_order_value": "Avg Order Value (R$)",
        },
        title="Avg Order Value and Cancellation Rate by Installment Bucket",
    )

    fig.add_scatter(
        x=df[x_col],
        y=df["cancellation_rate_pct"],
        mode="lines+markers",
        name="Cancellation Rate %",
        yaxis="y2",
        line=dict(color="firebrick", width=2),
        marker=dict(size=8),
    )

    fig.update_layout(
        yaxis2=dict(
            title="Cancellation Rate %",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(x=0.01, y=0.99),
        height=450,
    )
    return fig


# ── RFM Segmentation ─────────────────────────────────────────────

def rfm_scatter(df: pd.DataFrame) -> alt.Chart:
    """
    Altair scatter: R score vs M score, colored by segment, sized by total spend.

    Args:
        df: Sampled RFM DataFrame. Must contain r_score, m_score, segment,
            total_spend, total_orders, days_since_last_order columns.
            Produced by services.transforms.sample_rfm_for_chart().

    Returns:
        Altair Chart object (interactive, call st.altair_chart() on it).
    """
    return (
        alt.Chart(df)
        .mark_circle(opacity=0.6)
        .encode(
            x=alt.X("r_score:O",
                    title="Recency Score (5 = most recent)",
                    axis=alt.Axis(labelAngle=0)),
            y=alt.Y("m_score:O",
                    title="Monetary Score (5 = highest spend)"),
            color=alt.Color("segment:N",
                            title="Segment",
                            legend=alt.Legend(orient="right")),
            size=alt.Size("total_spend:Q",
                          title="Total Spend (R$)",
                          scale=alt.Scale(range=[20, 400])),
            tooltip=[
                "segment",
                "r_score",
                "m_score",
                alt.Tooltip("total_spend:Q", format=".2f"),
                alt.Tooltip("total_orders:Q"),
                alt.Tooltip("days_since_last_order:Q"),
            ],
        )
        .properties(
            title="RFM Scatter — Recency vs Monetary Score by Segment",
            height=500,
        )
        .interactive()
    )