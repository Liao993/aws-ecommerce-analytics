-- Stub: built in Epic 4
-- Staging view for olist_sellers.
-- SCD Type 2 source — seller_id is the business key.
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_sellers') }}
