{% snapshot sellers_snapshot %}

{{
    config(
        target_schema  = 'staging',
        unique_key     = 'seller_id',
        strategy       = 'check',
        check_cols     = ['zip_code_prefix', 'seller_city', 'seller_state'],
    )
}}

-- Same rationale as customers_snapshot: snapshot from staging, not raw.
-- Seller location affects delivery delay analysis — we need the seller's
-- state at the time of each order, not their current state.
select
    seller_id,
    zip_code_prefix,
    seller_city,
    seller_state
from {{ ref('stg_sellers') }}

{% endsnapshot %}