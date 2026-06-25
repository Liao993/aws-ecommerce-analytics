{{ config(materialized='table') }}

/*
  mart_seller_performance
  -----------------------
  Aggregates to seller grain. Scores sellers on revenue and review quartiles.
  Business question: Which sellers are high-revenue but low-rated (or vice versa)?

  Key metrics:
    revenue_quartile  — NTILE(4) on total_revenue. 4 = top 25% revenue sellers.
    review_quartile   — NTILE(4) on avg_review_score. 4 = top 25% review sellers.
    on_time_rate      — % of this seller's orders delivered on or before estimated date.
*/

with seller_orders as (
    select
        oi.seller_id,
        oi.seller_state,
        oi.seller_city,
        o.order_id,
        o.total_order_value,
        o.review_score,
        o.is_on_time,
        o.delivery_delay_days,
        o.order_purchase_timestamp
    from {{ ref('int_order_items_enriched') }}  oi
    left join {{ ref('int_orders_enriched') }}  o
        on oi.order_id = o.order_id
    where o.order_status = 'delivered'
),

seller_agg as (
    select
        seller_id,
        seller_state,
        seller_city,
        count(distinct order_id)            as order_count,
        sum(total_order_value)              as total_revenue,
        avg(review_score)                   as avg_review_score,
        avg(is_on_time)                     as on_time_rate,
        avg(delivery_delay_days)            as avg_delay_days,
        min(order_purchase_timestamp)        as first_order_date,
        max(order_purchase_timestamp)        as last_order_date
    from seller_orders
    group by seller_id, seller_state, seller_city
),

final as (
    select
        seller_id,
        seller_state,
        seller_city,
        order_count,
        round(total_revenue, 2)             as total_revenue,
        round(avg_review_score, 2)          as avg_review_score,
        round(on_time_rate * 100, 1)        as on_time_pct,
        round(avg_delay_days, 1)            as avg_delay_days,

        -- Revenue quartile: 4 = top earners, 1 = bottom
        ntile(4) over (order by total_revenue asc)      as revenue_quartile,

        -- Review quartile: 4 = best rated, 1 = worst
        ntile(4) over (order by avg_review_score asc)   as review_quartile,

        -- Active months: months between first and last order (tenure on platform)
        datediff('month', first_order_date, last_order_date) + 1  as active_months,

        -- Review score bucket: categorical grouping for dashboard filters
        case
            when avg_review_score >= 4.0 then 'High (4-5)'
            when avg_review_score >= 3.0 then 'Medium (3-4)'
            else 'Low (<3)'
        end                                             as review_score_bucket

    from seller_agg
)

select * from final