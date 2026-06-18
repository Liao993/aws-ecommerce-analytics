{{ config(materialized='view') }}

with source as (
    select * from {{ source('dev_raw', 'olist_sellers') }}
),

renamed as (
    select
        -- Keys
        seller_id,
        {{ dbt_utils.generate_surrogate_key(['seller_id']) }}          as seller_key,

        -- Attributes
        cast(seller_zip_code_prefix as varchar(16))    as zip_code_prefix,
        seller_city                                     as city,
        seller_state                                    as state

    from source
)

select * from renamed
