{{ config(materialized='view') }}

with source as (
    select * from {{ source('dev_raw', 'olist_products') }}
),
translation as (
     select * from {{ ref('product_category_name_translation') }}
),

renamed as (
    select
        -- Keys
        product_id,
        {{ dbt_utils.generate_surrogate_key(['product_id']) }}         as product_key,

        -- Attributes
        product_category_name                                           as category_name,
        product_name_lenght                                             as name_length,       -- intentional typo from source
        product_description_lenght                                      as description_length,
        product_photos_qty                                              as photos_qty,
        cast(product_weight_g      as decimal(10,2))                   as weight_g,
        cast(product_length_cm     as decimal(10,2))                   as length_cm,
        cast(product_height_cm     as decimal(10,2))                   as height_cm,
        cast(product_width_cm      as decimal(10,2))                   as width_cm

    from source
)

select * from renamed
