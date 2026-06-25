{{ config(materialized='table') }}

/*
  mart_category_performance
  ----------------------------------
  Aggregates by product category (English name).
  Business question: Which categories generate the most revenue,
  and which have the worst reviews or delivery delays?

  Grain: one row per category_name_english.
*/

with items as (
    select * from {{ ref('int_order_items_enriched') }}
),

orders as (
    select order_id, review_score, delivery_delay_days, order_status
    from {{ ref('int_orders_enriched') }}
),

final as (
    select
        i.category_name_english,
        count(distinct i.order_id)          as order_count,
        count(*)                            as item_count,
        round(sum(i.price), 2)              as total_revenue,
        round(avg(i.price), 2)              as avg_item_price,
        round(avg(i.freight_value), 2)      as avg_freight_value,
        round(avg(i.freight_pct_of_price), 1) as avg_freight_pct,
        round(avg(o.review_score), 2)       as avg_review_score,
        round(avg(o.delivery_delay_days), 1) as avg_delay_days,
        round(avg(i.weight_g), 0)           as avg_weight_g
    from items i
    left join orders o on i.order_id = o.order_id
    where i.category_name_english is not null
      and o.order_status = 'delivered'
    group by i.category_name_english
)

select * from final
order by total_revenue desc