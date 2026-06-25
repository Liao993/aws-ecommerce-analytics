{{ config(materialized='table') }}

/*
  mart_customer_cohorts
  ----------------------
  Cohort analysis: groups customers by their first purchase month.
  Measures repeat purchase rates at 30, 60, and 90 days.

  Grain: one row per customer_unique_id.
*/

with customer_orders as (
    -- Fixed: points to the exact name of your intermediate model
    select * from {{ ref('int_customer_enriched') }}
),

customer_summary as (
    select
        customer_unique_id,
        cohort_month,
        min(first_order_timestamp)                              as first_order_date,
        max(order_purchase_timestamp)                           as last_order_date,
        count(distinct order_id)                                as total_orders,
        max(days_since_first_order)                             as customer_tenure_days,

        -- Repeat purchase flags: Check if any subsequent order fell into these day windows
        max(case when days_since_first_order between 1 and 30  and order_sequence > 1 then 1 else 0 end)
                                                                as repeat_within_30d,
        max(case when days_since_first_order between 1 and 60  and order_sequence > 1 then 1 else 0 end)
                                                                as repeat_within_60d,
        max(case when days_since_first_order between 1 and 90  and order_sequence > 1 then 1 else 0 end)
                                                                as repeat_within_90d
    from customer_orders
    group by customer_unique_id, cohort_month
)

select
    customer_unique_id,
    cohort_month,
    first_order_date,
    last_order_date,
    total_orders,
    customer_tenure_days,
    repeat_within_30d,
    repeat_within_60d,
    repeat_within_90d,
    case when total_orders > 1 then 1 else 0 end as is_repeat_customer
from customer_summary