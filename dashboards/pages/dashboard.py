"""
pages/dashboard.py — Core 5-tab analytics dashboard

Single responsibility: lay out the five core dashboard tabs and wire
together the backend query functions, service transforms, chart components,
and UI elements. No SQL, no pandas reshaping, no chart config lives here —
this file is layout and data orchestration only.

Tabs:
  1 — Seller Performance    : NTILE heatmap (revenue × review quartile)
  2 — Delivery Delays       : Top 15 corridors horizontal bar
  3 — Customer Retention    : Cohort heatmap (month × 30/60/90d)
  4 — Payment Behavior      : Dual-axis bar (AOV + cancellation rate)
  5 — RFM Segmentation      : Altair scatter (R vs M, colored by segment)
"""

import streamlit as st # type: ignore

from backend.dashboard_queries import (
    load_seller_performance,
    load_delivery_analysis,
    load_cohort_retention,
    load_payment_behavior,
    load_rfm_segmentation,
)
from services.transforms import (
    pivot_seller_heatmap,
    sort_corridors_by_delay,
    format_cohort_month,
    melt_retention_for_heatmap,
    cast_rfm_types,
    sample_rfm_for_chart,
)
from components.charts import (
    seller_heatmap,
    delivery_corridor_bar,
    cohort_heatmap,
    payment_dual_axis,
    rfm_scatter,
)
from components.ui_elements import (
    data_expander,
    metric_row,
    info_callout,
)


def render() -> None:
    """
    Entry point called by app.py. Renders the full 5-tab dashboard page.
    """
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Seller Performance",
        "🚚 Delivery Delays",
        "🔄 Customer Retention",
        "💳 Payment Behavior",
        "🎯 RFM Segmentation",
    ])

    # ── Tab 1: Seller Performance ─────────────────────────────────
    with tab1:
        st.subheader("📊 Seller Performance Matrix")
        st.write(
            "Revenue quartile vs review score quartile. Each cell shows the average "
            "on-time delivery rate. **Revenue Risk** sellers (Q4 revenue, Q1–Q2 review) "
            "are the highest-priority intervention targets."
        )

        df_seller = load_seller_performance()
        pivot = pivot_seller_heatmap(df_seller)
        st.plotly_chart(seller_heatmap(pivot), use_container_width=True)

        with st.expander("📌 Revenue Risk Sellers (Q4 Revenue, Q1–Q2 Review)"):
            risk = df_seller[
                (df_seller["revenue_quartile"] == 4) &
                (df_seller["review_quartile"] <= 2)
            ].sort_values("total_revenue", ascending=False).head(10)
            st.dataframe(
                risk[["seller_id", "seller_state", "total_revenue",
                      "avg_review_score", "on_time_pct", "order_count"]],
                use_container_width=True,
            )

    # ── Tab 2: Delivery Delays ────────────────────────────────────
    with tab2:
        st.subheader("🚚 Top 15 Worst Delivery Corridors")
        st.write(
            "Origin state → destination state corridors ranked by average delivery delay. "
            "Corridors with fewer than 10 orders are excluded (statistical reliability). "
            "**Note:** Olist pads estimates 10–14 days conservatively — all corridors "
            "appear 'early' relative to estimates. Focus on absolute delivery days, not delay days."
        )

        df_delivery = load_delivery_analysis()
        df_sorted = sort_corridors_by_delay(df_delivery)
        st.plotly_chart(delivery_corridor_bar(df_sorted), use_container_width=True)

    # ── Tab 3: Customer Retention ─────────────────────────────────
    with tab3:
        st.subheader("🔄 Customer Cohort Retention")
        st.write(
            "Each row is an acquisition cohort (month of first purchase). "
            "Columns show the % of that cohort who made a repeat purchase "
            "within 30, 60, or 90 days."
        )

        df_cohort = load_cohort_retention()
        df_cohort = format_cohort_month(df_cohort)
        _, heatmap_pivot = melt_retention_for_heatmap(df_cohort)
        st.plotly_chart(cohort_heatmap(heatmap_pivot), use_container_width=True)

        info_callout(
            "Retention rates are near 0% across all cohorts — this is a known "
            "characteristic of the Olist dataset. The platform was in pure acquisition "
            "mode in 2016–2018. This is itself the finding."
        )
        data_expander(df_cohort, "📊 Raw cohort data")

    # ── Tab 4: Payment Behavior ───────────────────────────────────
    with tab4:
        st.subheader("💳 Payment Behavior by Installment Count")
        st.write(
            "Does paying in more installments predict a larger basket? "
            "The bars show average order value (AOV); the line shows cancellation rate %."
        )

        df_payment = load_payment_behavior()
        st.plotly_chart(payment_dual_axis(df_payment, x_col="dimension_value"),
                        use_container_width=True)

    # ── Tab 5: RFM Segmentation ───────────────────────────────────
    with tab5:
        st.subheader("🎯 RFM Customer Segmentation")
        st.write(
            "Recency score (R) vs Monetary score (M), colored by segment label. "
            "Point size = total spend. Use the segment filter to isolate a group."
        )

        df_rfm = load_rfm_segmentation()
        df_rfm = cast_rfm_types(df_rfm)

        segments = sorted(df_rfm["segment"].unique())
        selected = st.multiselect("Filter by segment", segments, default=segments)
        df_filtered = df_rfm[df_rfm["segment"].isin(selected)]
        df_sampled = sample_rfm_for_chart(df_filtered)

        st.altair_chart(rfm_scatter(df_sampled), use_container_width=True)

        metric_row([
            {"label": "Total Customers",  "value": f"{len(df_rfm):,}"},
            {"label": "Champions",        "value": f"{(df_rfm['segment'] == 'Champion').sum():,}"},
            {"label": "At Risk",          "value": f"{(df_rfm['segment'] == 'At Risk').sum():,}"},
            {"label": "Lost",             "value": f"{(df_rfm['segment'] == 'Lost').sum():,}"},
        ])

if __name__ == "__main__":
    # For local dev: run this page standalone in Streamlit
    st.set_page_config(
        page_title="Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render()