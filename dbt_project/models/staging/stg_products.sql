{{ config(materialized='view') }}

with source as (
    select * from {{ source('raw', 'olist_products') }}
),
translation as (
     select * from {{ ref('product_category_name_translation') }}
),

renamed as (
    select
        -- Keys
        s.product_id,
        {{ dbt_utils.generate_surrogate_key(['s.product_id']) }} as product_key,

        -- Attributes
        s.product_category_name                                   as category_name_pt,
        coalesce(t.product_category_name_english, 'unknown')     as category_name_en,
        s.product_name_lenght                                     as name_length,       -- intentional typo from source
        s.product_description_lenght                              as description_length,
        s.product_photos_qty                                      as photos_qty,
        cast(s.product_weight_g   as decimal(10,2))               as weight_g,
        cast(s.product_length_cm  as decimal(10,2))               as length_cm,
        cast(s.product_height_cm  as decimal(10,2))               as height_cm,
        cast(s.product_width_cm   as decimal(10,2))               as width_cm

    from source as s
    left join translation as t 
        on s.product_category_name = t.product_category_name
)

select * from renamed
