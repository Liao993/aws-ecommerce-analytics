-- Stub: built in Epic 4
-- Staging view for product_category_name_translation.
-- Reference/lookup table: Portuguese → English category names.
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'product_category_name_translation') }}
