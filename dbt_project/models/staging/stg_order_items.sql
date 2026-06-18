{{ config(materialized='view') }}

with source as (
    select * from {{ source('dev_raw', 'olist_order_items') }}
),

renamed as (
    select
        -- Keys
        order_id,
        order_item_id,
        product_id,
        seller_id,
        {{ dbt_utils.generate_surrogate_key(['order_id', 'order_item_id']) }} as order_item_key,

        -- Timestamps
        cast(shipping_limit_date as timestamp)         as shipping_limit_date,

        -- Metrics
        cast(price         as decimal(10,2))           as price,
        cast(freight_value as decimal(10,2))           as freight_value

    from source
)

select * from renamed
