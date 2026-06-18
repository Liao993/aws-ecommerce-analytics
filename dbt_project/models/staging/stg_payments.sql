{{ config(materialized='view') }}

with source as (
    select * from {{ source('dev_raw', 'olist_order_payments') }}
),

renamed as (
    select
        -- Keys
        order_id,
        payment_sequential,
        {{ dbt_utils.generate_surrogate_key(['order_id', 'payment_sequential']) }} as payment_key,

        -- Attributes
        payment_type,
        payment_installments,
        cast(payment_value as decimal(10,2))           as payment_value

    from source
)

select * from renamed
