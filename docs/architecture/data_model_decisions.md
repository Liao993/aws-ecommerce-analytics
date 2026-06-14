# Data Model Decisions — Olist AWS Analytics Platform

This document records every non-obvious modeling decision made during Epic 3. It is structured as a decision log: what was chosen, what was rejected, why, and what the trade-off costs. Use this document to prepare interview answers — each section is a 60-second talking point.

---

## Decision 1: Star Schema over Snowflake Schema

**What we chose:** Star schema — denormalized dimensions joined directly to fact tables.

**What we rejected:** Snowflake schema — further normalizing dimensions into sub-tables (e.g., splitting `dim_products` into a separate `dim_categories` table).

**Why we chose this:**
Olist's dimension tables are small. `dim_products` has ~33K rows; `dim_sellers` has ~3K. At this scale, the additional join a snowflake schema requires adds query complexity without a meaningful performance benefit. Star schema mart queries are a single join from fact to dimension — readable, fast, and easy to explain.

Snowflake schemas make sense when dimensions are very wide (hundreds of columns) or when storage is constrained. Neither applies here.

**Trade-off cost:** Some redundancy in dimension tables (e.g., `product_category_name` stored in `dim_products` even though it could live in a separate `dim_categories`). Acceptable at Olist scale.

**Interview talking point:** "I chose star schema because the dimensions are small enough that denormalization doesn't create meaningful storage cost, but it does create meaningful query simplicity — every mart query is one join, not three."

---

## Decision 2: Primary Fact Grain — Item Level, Not Order Level

**What we chose:** `fact_order_items` at item grain — one row per item per order (composite key: `order_id` + `order_item_id`).

**What we rejected:** `fact_orders` at order grain — one row per order.

**Why we chose this:**
Grain is the most consequential decision in dimensional modeling. The rule is: *choose the finest grain that answers all your business questions without requiring a subquery back to the source.*

At order grain, you lose the ability to answer:
- "Which product category has the highest average freight value?"
- "Which seller has the best on-time rate per SKU?"
- "What is the revenue contribution of 'health and beauty' vs 'electronics'?"

All of these require item-level detail. At item grain, order-level questions still work — you just `GROUP BY order_id`. You never lose information by choosing finer grain; you do by choosing coarser grain.

**Trade-off cost:** `fact_order_items` is larger than `fact_orders` (~112K rows vs ~99K rows). Negligible at Olist scale; would require partitioning strategy at tens-of-millions scale.

[ADD YOUR OWN OBSERVATION: After running the row count query in Feature 3.1, note the actual difference in row count between orders and order_items here.]

**Interview talking point:** "Grain is the most important decision in dimensional modeling. I chose item grain because it answers every analytical question — category revenue, seller performance, freight analysis — without requiring a subquery back to the source table. You can always roll up from fine grain; you can't drill down from coarse grain."

---

## Decision 3: Three Fact Tables, Not One

**What we chose:** Separate fact tables for `fact_order_items`, `fact_orders`, and `fact_payments`.

**What we rejected:** A single combined fact table.

**Why we chose this:**
Each fact table has a different grain. Combining tables with different grains creates a **fan-out problem**: if a single order has 3 items and 2 payment records, joining them directly would produce 6 rows (3 × 2) — inflating every metric by the cross-product.

The solution is to keep each grain in its own fact table:
- `fact_order_items`: grain = item in order
- `fact_orders`: grain = order
- `fact_payments`: grain = payment record within order

Mart models that need cross-fact analysis (e.g., revenue + payment method) join through a shared dimension or bridge table, not by combining facts directly.

**Trade-off cost:** Three fact tables requires analysts to know which table to start from for a given question. Addressed by good table naming and clear documentation in the Streamlit dashboard.

**Interview talking point:** "Each fact table has a different grain. If you combine tables with different grains, you get a fan-out: a 3-item order with 2 payment rows becomes 6 rows in the join. The fix is one fact table per grain."

---

## Decision 4: SCD Type 2 for Customers and Sellers

**What we chose:** SCD Type 2 for `dim_customers` and `dim_sellers` — historical rows preserved with `dbt_valid_from`, `dbt_valid_to`, and `is_current`.

**What we rejected:** SCD Type 1 — overwrite the current value when an attribute changes.

**Why we chose this:**
Customer city and seller state can change over time. If a customer moves from Vancouver to Toronto and you use SCD Type 1, all their historical orders now appear to have been placed from Toronto. This breaks:
- Geographic cohort analysis ("orders from BC in Q1 2017" would be wrong)
- Customer lifetime value calculations by region
- Seller performance benchmarks by state

SCD Type 2 preserves history. Each change creates a new row with a new `dbt_valid_from` date. The fact table join uses `customer_key` — the surrogate key — which points to the *specific version* of the customer at the time of the order. Historical accuracy is preserved automatically.

**Trade-off cost:** `dim_customers` becomes larger than the source `olist_customers` table (one row per version, not one row per customer). Queries against the current state must filter `WHERE is_current = TRUE`. Analysts who don't know about SCD 2 may double-count if they forget the filter.

[ADD YOUR OWN OBSERVATION: After building dim_customers in Epic 4, note here how many rows the SCD Type 2 dimension produced vs. the source table.]

**Interview talking point:** "SCD Type 2 preserves history. When a customer moves cities, instead of overwriting their record, we close the old row (set dbt_valid_to to today) and open a new row. Every historical order stays linked to the city the customer was in at the time of purchase."

> **📚 Further reading:** See the **SCD Deep Dive** child page nested under Feature 3.3 in Notion for a full walkthrough of SCD Type 1, 2, and 3 with before/after row examples.

---

## Decision 5: dim_date Generated in dbt, Not Sourced from Olist

**What we chose:** Generate `dim_date` in dbt using the `dbt_utils.date_spine()` macro, producing one row per calendar date from 2016-01-01 to 2019-12-31.

**What we rejected:** Deriving dates from `olist_orders.order_purchase_timestamp` (would only produce dates that have orders — missing weekends, holidays, and low-volume days).

**Why we chose this:**
A date dimension must be **complete** — every single calendar date in the range must have a row, even if no orders happened that day. Otherwise, time-series analysis has gaps: a weekly trend chart with missing Sundays looks like dips, not quiet days.

The `dbt_utils.date_spine()` macro generates a complete sequence of dates. We then add derived attributes (year, month, quarter, day_of_week, is_weekend) as calculated columns. The result is a calendar table that any fact table can join to, even if the source data has no rows for that date.

**Trade-off cost:** `dim_date` adds ~1,461 rows (4 years of daily dates). No meaningful storage cost. The macro must be run once with `dbt run --select dim_date` before any model that references it.

**Interview talking point:** "The Olist dataset has no date table. I generated one in dbt using date_spine, which produces a row for every calendar date in the range. This matters because you can't do trend analysis on dates that don't exist in your data — missing dates create false dips in time-series charts."

---

## Decision 6: Surrogate Keys via dbt_utils.generate_surrogate_key()

**What we chose:** `dbt_utils.generate_surrogate_key(['natural_key_column'])` to produce an md5 hash as the surrogate key in every dimension table.

**What we rejected:** Using natural keys (UUIDs) directly as join keys in fact tables; using a plain `md5()` SQL call without the macro.

**Why we chose this:**
Natural keys in Olist are UUID strings (32+ characters). Joining on long strings is slower than joining on hashes or integers at scale, and if the upstream key format ever changes, all downstream models break. A surrogate key decouples the join key from the source system.

`dbt_utils.generate_surrogate_key()` is preferred over a raw `md5()` call because:
1. It handles NULL values gracefully (raw md5 on a NULL column produces an incorrect result)
2. It is consistent across all dbt projects — colleagues reading your code know immediately what the key is
3. The resulting keys are testable with `not_null` and `unique` dbt schema tests

**Trade-off cost:** The surrogate key is an md5 hash (VARCHAR 32), not a sequential integer. Some analytical tools join faster on integers. At Olist scale, this is immaterial; at billions of rows, you'd reconsider.

**Interview talking point:** "I used dbt_utils.generate_surrogate_key instead of the raw md5() function because it handles NULL inputs safely, produces consistent results across models, and makes the intent immediately clear to anyone reading the code."

---

## Decision 7: Schema Naming Convention

**What we chose:** Explicit schema names per layer with environment prefix:
- Dev: `dev_raw`, `dev_staging`, `dev_intermediate`, `dev_marts`
- Prod: `raw`, `staging`, `intermediate`, `marts`

**What we rejected:** A single schema with environment toggled by profile target; using `public` schema; mixing dev and prod in the same schema.

**Why we chose this:**
Explicit schema names make the data lineage visible at a glance in any SQL client. You can look at a query and immediately know whether you're in dev or prod, and which transformation layer the data came from. The `dev_` prefix acts as a visual guardrail — you can't accidentally query a staging view thinking it's a mart table when the schema names are different.

In the dbt profiles.yml, the `schema` key is set to `dev` and dbt appends the layer suffix automatically (e.g., `dev_staging`). This avoids the double-suffix pitfall that CI pipelines hit when `schema` is set to `dev_staging` instead of `dev`.

**Trade-off cost:** More schemas to manage in Redshift. No meaningful operational cost.

**Interview talking point:** "Schema naming is the first thing a data engineer looks at to understand a project's structure. I chose explicit layer names with an environment prefix so any query tells you both where the data lives in the transformation pipeline and which environment it's in."

---

## Decision 8: Incremental Strategy — Merge with Lookback Window

**What we chose:** Incremental merge strategy with a 3-day lookback window for `stg_orders` and `stg_order_reviews`. Merge on natural key (`order_id`, `review_id`).

**What we rejected:** Full refresh on every dbt run; append-only incremental.

**Why we chose this:**
`olist_orders` rows change status over time — an order that was `shipped` on Monday becomes `delivered` on Thursday. A full refresh every run correctly handles this but wastes Redshift RPUs re-processing 100K rows when only the recent rows changed.

An append-only incremental would miss status changes entirely — an order that was `shipped` when first loaded would never update to `delivered`.

Merge with a 3-day lookback re-processes only rows where `order_purchase_timestamp >= current_date - 3` on incremental runs, while handling late-arriving status updates within the window. The lookback window is a trade-off between compute cost and late-data correctness.

**Trade-off cost:** Status changes older than 3 days won't be caught. For Olist's historical dataset this is theoretical — in production, you'd tune the lookback window based on the actual SLA for order status updates.

**Interview talking point:** "I used incremental merge with a 3-day lookback because orders change status over time. Append-only misses those updates. Full refresh is correct but wasteful. The lookback window is a configurable trade-off between compute cost and late-data correctness."

---

## Decision 9: mart_rfm_segmentation as a Materialized dbt Table

**What we chose:** RFM (Recency, Frequency, Monetary) customer segmentation as a `materialized='table'` dbt model in the marts layer.

**What we rejected:** RFM as a one-off SQL query in Redshift Query Editor; RFM as a view computed at Streamlit query time.

**Why we chose this:**
RFM segmentation is a recurring output — it changes every time new orders arrive. Materializing it as a dbt table means:
1. Streamlit queries it in milliseconds (pre-computed, indexed)
2. It is automatically refreshed every time the dbt pipeline runs (no manual re-run)
3. The computation happens in Redshift (where the data lives), not in Streamlit (which has limited memory)
4. It is tested with dbt schema tests — segment labels validated with `accepted_values`

**Trade-off cost:** An additional dbt model and Redshift table. Negligible at Olist scale.

**Interview talking point:** "I promoted RFM from a one-off query to a dbt mart model because it feeds the Streamlit dashboard and needs to refresh automatically. A view would recompute on every dashboard load — slow. A materialized table gives the dashboard sub-second response time."

---

## Decision 10: dim_geolocation Aggregated to One Row per Zip

**What we chose:** Aggregate `olist_geolocation` to one row per zip code prefix using the centroid (average lat/lng) of all points for that zip.

**What we rejected:** Loading all ~1M rows into `dim_geolocation`; joining customers and sellers to the multi-row geolocation table with a fan-out.

**Why we chose this:**
The raw `olist_geolocation` table has multiple lat/lng coordinates per zip code — representing the full set of delivery points in that postal zone. Joining `dim_customers` (one row per customer) to this multi-row table without aggregation would produce duplicate customer rows in every fact query.

Aggregating to a centroid (one row per zip, average lat/lng) is a practical simplification that enables geographic analysis without the fan-out problem. For the Streamlit dashboard's map visualizations, a zip-level centroid is accurate enough.

**Trade-off cost:** Precision loss on geographic coordinates. Fine for customer distribution maps; not appropriate for exact delivery routing.

**Interview talking point:** "The raw geolocation table has multiple rows per zip code. I aggregated it to a centroid before joining to customers and sellers to prevent the fan-out that would inflate every downstream metric."