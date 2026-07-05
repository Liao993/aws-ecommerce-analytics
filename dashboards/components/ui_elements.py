"""
components/ui_elements.py — Reusable Streamlit UI fragments

Single responsibility: render common Streamlit UI patterns (metric rows,
section headings, callout boxes, data expanders) that appear in more than
one page. Each function calls st.* directly and returns None.

Keeping these here rather than in page files means:
  - A metric card style change touches one file, not five
  - Page files stay focused on layout and data wiring
"""

import streamlit as st  # type: ignore
import pandas as pd  # type: ignore


def page_header(title: str, subtitle: str) -> None:
    """
    Render a consistent page title + subtitle block.

    Args:
        title:    H2-level heading string (no emoji needed — caller adds it).
        subtitle: Explanatory sentence displayed as st.caption.
    """
    st.subheader(title)
    st.caption(subtitle)


def metric_row(metrics: list[dict]) -> None:
    """
    Render a row of st.metric cards.

    Args:
        metrics: List of dicts, each with keys:
                 - label (str)
                 - value (str | int | float)
                 - delta (str | None, optional)

    Example:
        metric_row([
            {"label": "Total Customers", "value": "94,990"},
            {"label": "Champions", "value": "1,234", "delta": "+12%"},
        ])
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        col.metric(
            label=m["label"],
            value=m["value"],
            delta=m.get("delta"),
        )


def data_expander(df: pd.DataFrame, label: str = "📋 Raw data", n: int = 100) -> None:
    """
    Show the first n rows of a DataFrame inside a collapsed expander.

    Args:
        df:    DataFrame to display.
        label: Expander label string.
        n:     Max rows to show (default 100 — avoids rendering 100K rows).
    """
    with st.expander(label):
        st.dataframe(df.head(n), use_container_width=True)


def info_callout(text: str) -> None:
    """
    Render an st.info box — used for findings and caveats inline with charts.

    Args:
        text: Markdown-formatted string to display.
    """
    st.info(text)