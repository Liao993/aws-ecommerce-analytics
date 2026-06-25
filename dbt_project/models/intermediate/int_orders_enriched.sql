{{ config(materialized='view') }}

/*
  int_orders_enriched
  -------------------
  Joins orders → customers → payments → reviews into one enriched row per order.

  Key derived columns (computed here, not available in staging):
    delivery_delay_days  — datediff(estimated, actual). Single definition. Pass through downstream, never recompute.
    is_on_time           — 1 if delivered on or before estimated date.
    total_order_value    — sum of all payment values for this order.
    review_score         — most recent review per order (orders can have multiple).
    customer_state       — kept here even though delivery analysis now joins customers
                           directly, because mart_seller_performance also needs it.

  Grain: one row per order_id.
  Consumers: mart_seller_performance, mart_rfm_segmentation, mart_payment_behavior,
             mart_product_category_performance, int_delivery_analysis (for delay cols only),
             int_customer_orders.
*/

with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),
payments as (
    -- Aggregate to order grain: one order can have multiple payment rows (installments)
    select
        order_id,
        sum(payment_value)          as total_order_value,
        max(payment_installments)   as max_installments,
        count(*)                    as payment_count
    from {{ ref('stg_payments') }}
    group by order_id
),

reviews as (
    -- Take the most recent review per order (some orders have duplicate review_ids) - Clients may update reviews after customer service responds
    select
        order_id,
        review_score,
        review_creation_date,
        row_number() over (
            partition by order_id
            order by review_creation_date desc
        ) as review_rank
    from {{ ref('stg_reviews') }}
),

final as (
    select
        -- Order keys
        o.order_id,
        o.order_key,
        o.customer_id,


        -- Order lifecycle
        o.order_status,
        o.order_purchase_timestamp,
        o.order_approved_at,
        o.order_delivered_carrier_date,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,

        -- Derived: delivery performance
        -- Positive = late. Negative = early. NULL = not yet delivered.
        datediff(
            'day',
            o.order_estimated_delivery_date,
            o.order_delivered_customer_date
        )                                          as delivery_delay_days,

        -- Derived: was this order delivered on time?
        case
            when o.order_delivered_customer_date <= o.order_estimated_delivery_date then 1
            else 0
        end                                        as is_on_time,

        -- Payment summary
        coalesce(p.total_order_value, 0)           as total_order_value,
        p.max_installments,
        p.payment_count,

        -- Review (most recent only)
        r.review_score,
        r.review_creation_date,

        -- Geography
        c.customer_state                           as customer_state

    from orders o
    left join payments p
        on o.order_id = p.order_id
    left join customers c
        on o.customer_id = c.customer_id
    left join reviews r
        on o.order_id = r.order_id
        and r.review_rank = 1
)

select * from final