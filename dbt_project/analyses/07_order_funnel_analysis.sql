/*
  Analysis: Order Funnel Analysis
  =================================
  Business Question : At which stage of the order lifecycle do orders drop off most,
                      and what percentage of created orders successfully reach delivery?
  SQL Pattern       : UNION ALL to stack funnel stages into a single column;
                      COUNT(DISTINCT) per stage; LAG() to compute stage-over-stage
                      drop-off percentage
  Tables Used       : dev_staging.stg_orders

Finding           : 97.0% of created orders successfully reach 'delivered' status. There is
                     no single dominant drop-off stage — losses are small and distributed
                     across the lifecycle, with the largest individual drops at
                     created→approved (-1.2%) and shipped→delivered (-1.1%). The fulfillment
                     middle of the funnel (invoiced→processing→shipped) shows minimal loss
                     (-0.3% each).

So What           : Olist's fulfillment pipeline is healthy overall — there's no single stage
                     to target for a major completion-rate fix. The created→approved drop
                     (likely payment approval failures) and shipped→delivered drop (likely
                     late-stage cancellations or delivery failures) are the two stages worth
                     investigating first to push completion above 97%, but neither is a
                     structural bottleneck.
                     
Interview Angle   : "Funnel analysis in SQL uses UNION ALL to avoid wide pivots — each stage
                     is one SELECT block, making it easy to add new stages. LAG() computes
                     drop-off by comparing each row to the one above it in stage order.
                     NULLIF prevents division by zero when a stage has zero events. One
                     design choice worth calling out: each stage's WHERE clause is
                     cumulative-inclusive, so canceled and unavailable orders silently exit
                     the funnel after stage 1 rather than appearing as an explicit drop-off —
                     I'd extend this with dedicated terminal stages if I needed the funnel to
                     account for 100% of orders rather than just the live fulfillment path."

*/

WITH funnel_stages AS (
    -- Each SELECT represents one stage of the Olist order lifecycle
    -- Stage order follows the Olist order status progression
    SELECT 1 AS stage_order, 'created'     AS stage_name, COUNT(DISTINCT order_id) AS stage_count
    FROM {{ ref('stg_orders') }} WHERE order_status IN ('created','approved','invoiced','processing','shipped','delivered','canceled','unavailable')
    UNION ALL
    SELECT 2, 'approved',  COUNT(DISTINCT order_id)
    FROM {{ ref('stg_orders') }} WHERE order_status IN ('approved','invoiced','processing','shipped','delivered')
    UNION ALL
    SELECT 3, 'invoiced',  COUNT(DISTINCT order_id)
    FROM {{ ref('stg_orders') }} WHERE order_status IN ('invoiced','processing','shipped','delivered')
    UNION ALL
    SELECT 4, 'processing', COUNT(DISTINCT order_id)
    FROM {{ ref('stg_orders') }} WHERE order_status IN ('processing','shipped','delivered')
    UNION ALL
    SELECT 5, 'shipped',   COUNT(DISTINCT order_id)
    FROM {{ ref('stg_orders') }} WHERE order_status IN ('shipped','delivered')
    UNION ALL
    SELECT 6, 'delivered', COUNT(DISTINCT order_id)
    FROM {{ ref('stg_orders') }} WHERE order_status = 'delivered'
),

funnel_with_dropoff AS (
    SELECT
        stage_order,
        stage_name,
        stage_count,
        LAG(stage_count) OVER (ORDER BY stage_order)                AS prev_stage_count,
        ROUND(
            (stage_count - LAG(stage_count) OVER (ORDER BY stage_order))
            * 100.0 / NULLIF(LAG(stage_count) OVER (ORDER BY stage_order), 0)
        , 1)                                                        AS stage_change_pct,
        -- Overall conversion from stage 1 (top of funnel)
        ROUND(
            stage_count * 100.0 / NULLIF(FIRST_VALUE(stage_count)
                OVER (ORDER BY stage_order
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING), 0)
        , 1)                                                        AS pct_of_top_funnel
    FROM funnel_stages
)

SELECT
    stage_order,
    stage_name,
    stage_count,
    prev_stage_count,
    stage_change_pct                                                AS stage_over_stage_pct,
    pct_of_top_funnel
FROM funnel_with_dropoff
ORDER BY stage_order;