{{
    config(
        materialized = 'incremental',
        unique_key = 'order_key',
        incremental_strategy = 'merge'
    )
}}

with olist_orders as (

    select * from {{ source('dev_raw', 'olist_orders') }}


    {% if is_incremental() %}
        -- Lookback 3 days from the latest order already in this table.
        -- Why 3 days: late-arriving status updates (e.g. a delivered confirmation
        -- arriving in S3 after the pipeline ran) are caught on the next run
        -- without requiring a full rebuild of all 100K rows.
        where cast(order_purchase_timestamp as timestamp) >= (
            select max(order_purchase_timestamp) from {{ this }}
        ) - interval '3 days'
    {% endif %}

),

renamed as (

    select
        -- ── Keys ──────────────────────────────────────────────────────
        order_id,
        customer_id,

        -- Surrogate key: md5 of the natural key.
        -- Used in dbt relationships tests and as a stable join key
        -- downstream — protects against upstream PK type changes.
        {{ dbt_utils.generate_surrogate_key(['order_id']) }}   as order_key,

        -- ── Status ────────────────────────────────────────────────────
        order_status,

        -- ── Timestamps — explicit TIMESTAMP casts ─────────────────────
        -- Redshift stores these as VARCHAR from the Glue COPY.
        -- Casting here means every downstream model gets a real TIMESTAMP,
        -- not a string — no surprises in DATEDIFF or DATE_TRUNC calls.
        cast(order_purchase_timestamp      as timestamp)  as order_purchase_timestamp,
        cast(order_approved_at             as timestamp)  as order_approved_at,
        cast(order_delivered_carrier_date  as timestamp)  as order_delivered_carrier_date,
        cast(order_delivered_customer_date as timestamp)  as order_delivered_customer_date,
        cast(order_estimated_delivery_date as timestamp)  as order_estimated_delivery_date

    from olist_orders

)

select * from renamed