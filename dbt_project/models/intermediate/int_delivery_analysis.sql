{{ config(materialized='view') }}

/*
  int_delivery_analysis
  ----------------------
  One row per delivered order item with full delivery corridor context.

  DESIGN DECISION — staging directly vs intermediate models:

    This model joins STAGING TABLES directly for all raw/passthrough columns:
      stg_orders        — timestamps, order_status
      stg_order_items   — order_item_id, seller_id, price, freight_value
      stg_sellers       — seller_state (origin)
      stg_customers     — customer_state (destination)

    Why not pull these from int_order_items_enriched / int_orders_enriched?
    The rule: reuse intermediate models when you need their *derived* columns.
    seller_state, customer_state, and the delivery timestamps are pure passthroughs
    from staging — no computation has been applied to them. Routing through two
    intermediate models to retrieve passthrough columns adds a dependency we
    don't need and makes the lineage misleading (suggesting we need the full
    enriched dataset when we only need two columns).

    This model DOES still join int_orders_enriched — but only for two columns:
      delivery_delay_days  — computed there (datediff estimated vs actual)
      is_on_time           — computed there (boolean flag)
    These ARE derived, and their definition must live in exactly one place.
    Pulling them from int_orders_enriched enforces that single source of truth.

  Key derived columns computed here (new — not available from any upstream model):
    actual_delivery_days    — days from purchase to actual delivery
    estimated_delivery_days — days from purchase to estimated delivery
    corridor                — "origin_state → destination_state" label

  Grain: one row per order_item_id (delivered orders only).
  Filter: order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL.
  Consumer: mart_delivery_analysis.
*/

with orders as (
    select * from {{ ref('stg_orders') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

sellers as (
    select * from {{ ref('stg_sellers') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

-- Pull only the two computed columns from int_orders_enriched.
-- These are genuinely derived there and must not be recomputed.
order_metrics as (
    select
        order_id,
        delivery_delay_days,
        is_on_time
    from {{ ref('int_orders_enriched') }}
),

final as (
    select
        -- Keys
        oi.order_id,
        oi.order_item_id,
        oi.seller_id,

        -- Geography: origin (seller state) → destination (customer state)
        s.seller_state                                      as origin_state,
        c.customer_state                                    as destination_state,
        s.seller_state || ' → ' || c.customer_state        as corridor,

        -- Item context
        oi.price,
        oi.freight_value,

        -- Delivery timing (raw — from stg_orders directly)
        o.order_purchase_timestamp,
        o.order_estimated_delivery_date,
        o.order_delivered_customer_date,
        o.order_status,

        -- COMPUTED HERE: not available from any upstream model
        datediff(
            'day',
            o.order_purchase_timestamp,
            o.order_delivered_customer_date
        )                                                   as actual_delivery_days,

        datediff(
            'day',
            o.order_purchase_timestamp,
            o.order_estimated_delivery_date
        )                                                   as estimated_delivery_days,

        -- PASSED THROUGH from int_orders_enriched — do not recompute
        om.delivery_delay_days                              as delay_days,
        om.is_on_time

    from order_items oi
    left join orders    o  on oi.order_id  = o.order_id
    left join sellers   s  on oi.seller_id = s.seller_id
    left join customers c  on o.customer_id = c.customer_id
    left join order_metrics om on oi.order_id = om.order_id
    where o.order_status = 'delivered'
        and o.order_delivered_customer_date is not null
)

select * from final