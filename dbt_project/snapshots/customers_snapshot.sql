{% snapshot customers_snapshot %}

{{
    config(
        target_schema  = 'dev_staging',
        unique_key     = 'customer_id',
        strategy       = 'check',
        check_cols     = ['zip_code_prefix', 'city', 'state'],
    )
}}

-- Snapshot source: read from the staging model, not raw source.
-- Why staging, not raw: stg_customers already has clean column names and
-- correct types. Snapshotting from raw would mean tracking typo column names
-- like 'customer_zip_code_prefix' instead of 'zip_code_prefix'.
select
    customer_id,
    customer_unique_id,
    zip_code_prefix,
    city,
    state
from {{ ref('stg_customers') }}

{% endsnapshot %}