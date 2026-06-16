-- Stub: built in Epic 4
-- Staging view for olist_order_reviews.
-- review_id is ~95% unique (known Olist data quirk).
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_order_reviews') }}
