{{ config(materialized='view') }}

/*
  int_customer_orders_enriched
  ------------------------------
  Aggregates order history to the unique customer level.
  Provides the heavy-lifting calculations required for RFM segmentation,
  cohort analyses, and customer-centric retention logic.

  Key derived columns:
    recency_days            — Days elapsed since the customer's last order
    frequency_orders        — Total volume of orders placed by this unique customer
    monetary_value          — Total historical revenue spent by this customer
    avg_order_value         — Average basket size per order
    is_repeat_customer      — Flags if a customer has bought more than once (1 or 0)

  Grain: one row per customer_unique_id.
  Used by: mart_customer_cohorts, mart_rfm_segmentation.
*/

with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

-- Step 1: Pre-aggregate order item value to the order level
order_financials as (
    select
        order_id,
        sum(price)          as order_item_total,
        sum(freight_value)  as order_freight_total
    from order_items
    group by 1
),

-- Step 2: Combine orders, financials, and customer identifiers
orders_joined as (
    select
        o.order_id,
        c.customer_unique_id,
        o.order_purchase_timestamp,
        coalesce(f.order_item_total, 0) as order_value
    from orders o
    left join customers c
        on o.customer_id = c.customer_id
    left join order_financials f
        on o.order_id = f.order_id
    -- Standard practice for e-commerce metrics: exclude canceled/unavail orders
    where o.order_status not in ('canceled', 'unavailable')
),

-- Step 3: Aggregate directly to the Customer Grain
customer_aggregations as (
    select
        customer_unique_id,
        min(order_purchase_timestamp)   as first_order_timestamp,
        max(order_purchase_timestamp)   as last_order_timestamp,
        count(distinct order_id)        as frequency_orders,
        sum(order_value)                as monetary_value
    from orders_joined
    group by 1
),

-- Step 4: Final calculations for Customer behavior and metrics
final as (
    select
        customer_unique_id,
        first_order_timestamp,
        last_order_timestamp,
        frequency_orders,
        monetary_value,

        -- Derived Customer metrics
        case 
            when frequency_orders > 0 then round(monetary_value / frequency_orders, 2)
            else 0 
        end                                                     as avg_order_value,

        case when frequency_orders > 1 then 1 else 0 end        as is_repeat_customer,

        -- Recency: Days since last order relative to the current timestamp (or data ceiling)
        -- Note: In a live pipeline, you use CURRENT_TIMESTAMP. 
        -- For the static Olist dataset, using the max date in the system prevents massive recency values.
        datediff(
            'day', 
            last_order_timestamp, 
            (select max(order_purchase_timestamp) from orders)
        )                                                       as recency_days,

        -- Cohort analysis helper: Extract month of first acquisition
        date_trunc('month', first_order_timestamp)               as cohort_month

    from customer_aggregations
)

select * from final