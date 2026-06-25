{{ config(materialized='view') }}

/*
  int_customer_orders_enriched
  ------------------------------
  Enriches individual order data with customer identifiers, sequencing,
  and behavioral timelines. 

  Grain: one row per customer order.
*/

with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

-- Step 1: Pre-aggregate order item value to the order level
order_financials as (
    select
        order_id,
        sum(price)          as order_item_total,
        sum(freight_value)  as order_freight_total
    from order_items
    group by 1
),

-- Step 2: Combine orders, financials, and calculate customer-specific timelines
orders_sequenced as (
    select
        o.order_id,
        c.customer_unique_id,
        o.order_purchase_timestamp,
        coalesce(f.order_item_total, 0) as order_value,
        
        -- Order sequence per customer: 1 = first order, 2 = second, etc.
        row_number() over (
            partition by c.customer_unique_id 
            order by o.order_purchase_timestamp asc
        ) as order_sequence,

        -- Pull out the customer's definitive first purchase timestamp across all history
        min(o.order_purchase_timestamp) over (
            partition by c.customer_unique_id
        ) as first_order_timestamp

    from orders o
    left join customers c
        on o.customer_id = c.customer_id
    left join order_financials f
        on o.order_id = f.order_id
    where o.order_status not in ('canceled', 'unavailable')
),

-- Step 3: Compute final delta metrics at the order level
final as (
    select
        order_id,
        customer_unique_id,
        order_purchase_timestamp,
        order_value,
        order_sequence,
        first_order_timestamp,
        
        -- Calculated field requested for cohort analysis
        datediff('day', first_order_timestamp, order_purchase_timestamp) as days_since_first_order,
        
        -- Cohort month assignment
        date_trunc('month', first_order_timestamp) as cohort_month
    from orders_sequenced
)

select * from final