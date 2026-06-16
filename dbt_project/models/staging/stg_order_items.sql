-- Stub: built in Epic 4
-- Staging view for olist_order_items.
-- Grain: order_id + order_item_id (composite key).
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_order_items') }}
