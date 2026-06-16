-- Stub: built in Epic 4
-- Staging view for olist_customers.
-- SCD Type 2 source — customer_unique_id is the business key.
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_customers') }}
