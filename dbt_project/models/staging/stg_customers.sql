{{ config(materialized='view') }}

with source as (
    select * from {{ source('raw', 'olist_customers') }}
),

renamed as (
    select
        -- Keys
        -- IMPORTANT: customer_id is order-scoped (a new ID is generated per order).
        -- customer_unique_id is the true person identifier and persists across orders.
        -- The surrogate key is built on customer_unique_id so SCD Type 2 snapshots
        -- and RFM segmentation correctly identify the same person across multiple orders.
        -- customer_id is kept because fact_order_items joins via customer_id from olist_orders.
        customer_id,
        customer_unique_id,
        {{ dbt_utils.generate_surrogate_key(['customer_unique_id']) }}  as customer_key,

        -- Attributes
        cast(customer_zip_code_prefix as varchar(16))  as zip_code_prefix,
        customer_city                                   as city,
        customer_state                                  as customer_state

    from source
)

select * from renamed