-- Stub: built in Epic 4
-- Staging view for olist_geolocation.
-- Aggregated to one row per zip code (centroid lat/lng) in dim_geolocation.
{{ config(materialized='view') }}
select * from {{ source('dev_raw', 'olist_geolocation') }}
