"""
app.py — Olist E-Commerce Analytics Dashboard entry point

Single responsibility: configure the Streamlit app, render the top-level
navigation sidebar, and delegate to the correct page module.

No SQL, no chart logic, no pandas logic lives here. Every tab and chart
lives in its respective layer:

  backend/   → SQL queries + Redshift connection
  services/  → pandas transforms and utilities
  components/ → Plotly / Altair chart builders + UI widgets
  pages/     → Streamlit layout and data orchestration per page

Pages:
  📊 Dashboard         → pages/dashboard.py       (core 5-tab overview)
  🔍 Analyses Explorer → pages/analyses_explorer.py (7 deep-dive analyses)
"""

import os
from dotenv import load_dotenv # type: ignore
import streamlit as st # type: ignore

# Must be the first Streamlit call in the entry point
st.set_page_config(
    page_title="Olist Analytics",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load .env before any backend import — backend modules read env vars at import time
load_dotenv()



# ── App header ────────────────────────────────────────────────────

st.title("📦 Olist E-Commerce Analytics Platform")
st.caption(
    "Brazilian e-commerce orders 2016–2018 · "
    "Stack: AWS Glue → S3 → Redshift Serverless → dbt Core → Streamlit"
)



