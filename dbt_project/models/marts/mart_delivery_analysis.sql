{{ config(materialized='table') }}

/*
  mart_delivery_analysis
  -----------------------
  Aggregates delivery performance by origin-destination corridor.
  Business question: Which state-to-state routes have the worst delivery delays?

  Grain: one row per corridor (origin_state + destination_state).
*/

with delivery as (
    select * from {{ ref('int_delivery_analysis') }}
),

final as (
    select
        origin_state,
        destination_state,
        corridor,
        count(*)                                    as order_count,
        round(avg(delay_days), 1)                   as avg_delay_days,
        round(avg(actual_delivery_days), 1)         as avg_actual_delivery_days,
        round(avg(estimated_delivery_days), 1)      as avg_estimated_delivery_days,
        round(sum(case when is_on_time = 0 then 1 else 0 end)
              * 100.0 / count(*), 1)                as late_pct,
        round(avg(freight_value), 2)                as avg_freight_value
    from delivery
    group by origin_state, destination_state, corridor
    having count(*) >= 10  -- Filter corridors with < 10 orders (statistically unreliable)
)

select
    *,
    -- Rank corridors by delay: 1 = worst performer
    row_number() over (order by avg_delay_days desc)    as delay_rank
from final
order by avg_delay_days desc