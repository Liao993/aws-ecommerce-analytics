{{
    config(
        materialized         = 'incremental',
        unique_key           = ['order_id', 'order_item_id'],
        incremental_strategy = 'merge'
    )
}}

with source as (

    select * from {{ source('raw', 'olist_order_items') }}

    {% if is_incremental() %}
        -- Lookback 3 days. Using shipping_limit_date as the incremental column
        -- because it is always populated on order items (unlike order timestamps).
        where cast(shipping_limit_date as timestamp) >= (
            select max(shipping_limit_date) from {{ this }}
        ) - interval '3 days'
    {% endif %}

),

renamed as (

    select
        order_id,
        order_item_id,
        product_id,
        seller_id,
        -- Composite surrogate: order_item_id is only unique WITHIN an order
        {{ dbt_utils.generate_surrogate_key(['order_id', 'order_item_id']) }} as order_item_key,
        cast(shipping_limit_date as timestamp)  as shipping_limit_date,
        cast(price         as decimal(10,2))    as price,
        cast(freight_value as decimal(10,2))    as freight_value
    from source

)

select * from renamed
