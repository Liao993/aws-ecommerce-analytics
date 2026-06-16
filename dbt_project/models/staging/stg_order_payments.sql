-- Stub: built in Epic 4
-- Staging view for olist_order_payments.
-- Multiple rows per order (installments + payment types).
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_order_payments') }}
