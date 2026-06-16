-- Stub: built in Epic 4
-- Staging view for olist_products.
-- Joins product_category_name_translation for English category name.
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_products') }}
