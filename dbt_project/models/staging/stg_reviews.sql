{{ config(materialized='view') }}

with source as (
    select * from {{ source('dev_raw', 'olist_order_reviews') }}
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
        -- review_id is near-unique in the Olist source, but not a reliable PK.
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
