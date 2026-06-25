{{ config(materialized='table') }}

/*
  mart_payment_behavior
  ----------------------
  Aggregates orders by installment bucket AND by payment type.
  Business questions:
    - Do customers paying in more installments spend more per order?
    - Does payment type (credit card vs voucher vs boleto) predict basket size?
    - Which payment type has the highest cancellation rate?

  Two grains exposed via UNION ALL:
    1. installment_bucket grain  — for "does installment count correlate with spend?"
    2. payment_type grain        — for "which method drives AOV and cancellation?"

  Streamlit dashboard can filter by dimension_type to show either view.

  Grain: one row per installment_bucket OR payment_type (dimension_type column distinguishes).
*/

with orders as (
    select * from {{ ref('int_orders_enriched') }}
),

payments as (
    select * from {{ ref('stg_payments') }}
),

-- Join orders to payments to get payment_type alongside order metrics
orders_with_payments as (
    select
        o.order_id,
        o.order_status,
        o.total_order_value,
        o.review_score,
        o.max_installments,
        p.payment_type,
        p.payment_installments
    from orders o
    left join payments p on o.order_id = p.order_id
),

-- Grain 1: installment bucket
installment_agg as (
    select
        'installment_bucket'                            as dimension_type,
        case
            when max_installments = 1  then '1 (cash/single)'
            when max_installments <= 3 then '2-3'
            when max_installments <= 6 then '4-6'
            when max_installments <= 12 then '7-12'
            else '13+'
        end                                             as dimension_value,
        count(distinct order_id)                        as order_count,
        round(avg(total_order_value), 2)                as avg_order_value,
        round(sum(total_order_value), 2)                as total_revenue,
        round(avg(review_score), 2)                     as avg_review_score,
        round(avg(case when order_status = 'canceled' then 1.0 else 0.0 end) * 100, 1)
                                                        as cancellation_rate_pct
    from orders_with_payments
    where max_installments is not null
    group by 1, 2
),

-- Grain 2: payment type
payment_type_agg as (
    select
        'payment_type'                                  as dimension_type,
        payment_type                                    as dimension_value,
        count(distinct order_id)                        as order_count,
        round(avg(total_order_value), 2)                as avg_order_value,
        round(sum(total_order_value), 2)                as total_revenue,
        round(avg(review_score), 2)                     as avg_review_score,
        round(avg(case when order_status = 'canceled' then 1.0 else 0.0 end) * 100, 1)
                                                        as cancellation_rate_pct
    from orders_with_payments
    where payment_type is not null
    group by 1, 2
)

select * from installment_agg
union all
select * from payment_type_agg
order by dimension_type, order_count desc