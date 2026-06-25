{{ config(materialized='table') }}

/*
  mart_rfm_segmentation
  ----------------------
  Scores every customer on Recency, Frequency, and Monetary value.
  Assigns a segment label based on combined RFM score.

  R (Recency):   days since last order. Lower days = higher R score.
  F (Frequency): total number of orders. More orders = higher F score.
  M (Monetary):  total spend. Higher spend = higher M score.

  Scoring: NTILE(5) on each dimension. 5 = best, 1 = worst.

  Reference date: MAX(order_purchase_timestamp) from the dataset.
  Why not CURRENT_DATE: this is historical data ending in late 2018.
  Using CURRENT_DATE would make every R score = 1 (nobody ordered recently).

  Grain: one row per customer_unique_id.
*/

with orders as (
    select * from {{ ref('int_orders_enriched') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

-- Reference date: latest order in the dataset
reference_date as (
    select max(order_purchase_timestamp) as ref_date
    from orders
    where order_status = 'delivered'
),

customer_metrics as (
    select
        c.customer_unique_id,
        max(o.order_purchase_timestamp)         as last_order_date,
        count(distinct o.order_id)              as total_orders,
        round(sum(o.total_order_value), 2)      as total_spend,
        round(avg(o.review_score), 2)           as avg_review_score,
        min(o.order_purchase_timestamp)         as first_order_date,
        datediff('day',
            max(o.order_purchase_timestamp),
            (select ref_date from reference_date)
        )                                       as days_since_last_order
    from orders o
    left join customers c
        on o.customer_id = c.customer_id
    where o.order_status = 'delivered'
    group by c.customer_unique_id
),

rfm_scores as (
    select
        customer_unique_id,
        last_order_date,
        first_order_date,
        total_orders,
        total_spend,
        avg_review_score,
        days_since_last_order,

        -- R score: INVERT ntile because lower days_since = better recency
        -- ntile on days_since_last_order ASC: rank 1 = most recent = R score 5
        (6 - ntile(5) over (order by days_since_last_order asc))  as r_score,

        -- F score: more orders = higher score
        ntile(5) over (order by total_orders asc)                  as f_score,

        -- M score: higher spend = higher score
        ntile(5) over (order by total_spend asc)                   as m_score

    from customer_metrics
),

final as (
    select
        customer_unique_id,
        last_order_date,
        first_order_date,
        total_orders,
        total_spend,
        avg_review_score,
        days_since_last_order,
        r_score,
        f_score,
        m_score,
        r_score + f_score + m_score                 as rfm_total,

        -- Segment labels based on RFM total score
        case
            when r_score >= 4 and f_score >= 4 and m_score >= 4  then 'Champion'
            when r_score >= 3 and f_score >= 3                    then 'Loyal'
            when r_score >= 4 and f_score <= 2                    then 'New Customer'
            when r_score >= 3 and f_score <= 2 and m_score >= 3  then 'Potential Loyalist'
            when r_score <= 2 and f_score >= 3 and m_score >= 3  then 'At Risk'
            when r_score = 1 and f_score >= 3                     then 'Lost'
            when r_score <= 2 and m_score >= 4                    then 'Cant Lose Them'
            else 'Needs Attention'
        end                                         as segment

    from rfm_scores
)

select * from final