{{ config(materialized='view') }}

with source as (
    select * from {{ source('dev_raw', 'olist_geolocation') }}
),

-- Aggregate to one row per zip_code_prefix using centroid (average lat/lng).
-- The raw table has ~1M rows for ~19K unique zip codes — multiple coordinate
-- readings per zip. Without this aggregation, any join from customers or sellers
-- (which have one row per zip) to geolocation produces a fan-out: one customer
-- row multiplies into 50+ rows. Centroid aggregation eliminates the fan-out
-- and reduces the table from ~1M to ~19K rows.
-- city and state use MIN() as a stable tiebreaker — same zip always picks same city.
centroid as (
    select
        geolocation_zip_code_prefix                         as zip_code_prefix,
        avg(cast(geolocation_lat as decimal(18,15)))        as latitude,
        avg(cast(geolocation_lng as decimal(18,15)))        as longitude,
        min(geolocation_city)                               as city,
        min(geolocation_state)                              as state
    from source
    group by geolocation_zip_code_prefix
),

final as (
    select
        zip_code_prefix,
        {{ dbt_utils.generate_surrogate_key(['zip_code_prefix']) }}     as geolocation_key,
        latitude,
        longitude,
        city,
        state
    from centroid
)

select * from final