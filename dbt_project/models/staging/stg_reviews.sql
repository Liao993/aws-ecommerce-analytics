{{
    config(
        materialized         = 'incremental',
        unique_key           = 'review_key',
        incremental_strategy = 'merge'
    )
}}

with source as (

    select * from {{ source('raw', 'olist_order_reviews') }}

    {% if is_incremental() %}
        -- Filter early in the source CTE to optimize query costs and speed.
        -- Lookback 3 days from the latest review already in this destination table.
        where cast(review_creation_date as timestamp) >= (
            select max(review_creation_date) from {{ this }}
        ) - interval '3 days'
    {% endif %}

),

deduped as (

    select *,
        row_number() over (
            partition by review_id, order_id
            order by review_answer_timestamp desc nulls last
        ) as row_num
    from source

),

renamed as (

    select
        -- Keys
        review_id,
        order_id,
        {{ dbt_utils.generate_surrogate_key(['review_id', 'order_id']) }} as review_key,

        -- Attributes
        review_score,
        review_comment_title                                            as comment_title,
        review_comment_message                                          as comment_message,

        -- Timestamps
        cast(review_creation_date    as timestamp)    as review_creation_date,
        cast(review_answer_timestamp as timestamp)    as review_answer_timestamp

    from deduped
    where row_num = 1

)

select * from renamed