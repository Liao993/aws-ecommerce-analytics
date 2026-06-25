{{ config(materialized='view') }}

/*
  int_order_items_enriched
  ------------------------
  Joins order_items → products → sellers.

  Key derived columns:
    freight_pct_of_price    — freight as % of item price (seller cost signal)
    category_name_english   — English translation of Portuguese category name pulled from staging

  Grain: one row per order_item (order_id + order_item_id).
  Used by: mart_seller_performance, mart_product_category_performance.
*/

with order_items as (
    select * from {{ ref('stg_order_items') }}
),

products as (
    select * from {{ ref('stg_products') }}  -- Updated: This now carries both _pt and _en categories
),

sellers as (
    select * from {{ ref('stg_sellers') }}
),

final as (
    select
        -- Item keys
        oi.order_id,
        oi.order_item_id,
        oi.order_item_key,
        oi.product_id,
        oi.seller_id,

        -- Product attributes (Now directly cleaned from the updated stg_products)
        p.category_name_pt,
        p.category_name_en                                      as category_name_english,
        p.weight_g,
        p.photos_qty,
    
        -- Pricing
        oi.price,
        oi.freight_value,
        oi.shipping_limit_date,

        -- Derived: freight as a proportion of price
        -- Useful for identifying high-freight categories and seller efficiency
        case
            when oi.price > 0
            then round(oi.freight_value / oi.price * 100, 2)
            else null
        end                                                     as freight_pct_of_price,

          -- Geography
        s.seller_state                                     as seller_state
    

    from order_items oi
    left join products p
        on oi.product_id = p.product_id
    left join sellers s
        on oi.seller_id = s.seller_id
)

select * from final