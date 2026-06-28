/*
  Analysis: Delivery Delay Root Cause
  =====================================
  Business Question : Which origin-to-destination state corridors have the worst average
                      delivery delays, and how late are they?
  SQL Pattern       : SELECT + ORDER BY from pre-ranked mart; LIMIT for top-N
  Tables Used       : dev_marts.mart_delivery_analysis

  Finding           : Across all 223 corridors with ≥10 orders, no corridor averages a
                      positive delay — every route delivers early relative to Olist's
                      estimated delivery dates, which are padded conservatively by 10–14
                      days on average. The "worst" corridor MA→ES (rank 1) averages only
                      2 days ahead of its estimate (28 actual vs 30 estimated), while the
                      best corridors deliver 13+ days early. The platform-wide late rate
                      is 8–10% regardless of volume bucket, with no meaningful difference
                      between high-volume (500+ orders, 8.7% late) and low-volume
                      (10–99 orders, 9.6% late) corridors.

  So What           : Olist's delivery estimates are so conservative that average delay
                      as a ranking metric is misleading — nearly all orders arrive early.
                      A more actionable metric would be the absolute late rate (8–10%
                      platform-wide) and the actual delivery time in days.
                      The MA→ES and MA→BA corridors (both involving Maranhão as origin)
                      warrant investigation — long actual delivery times of 21–28 days
                      suggest last-mile logistics gaps in the northeast, even if they
                      technically beat their padded estimates. Olist should tighten
                      delivery estimates for short-haul routes (e.g. DF→DF: 5 actual
                      days vs 13 estimated) and audit northeast corridors for
                      carrier performance.
                      
  Interview Angle   : "I filtered corridors with fewer than 10 orders in the mart model to
                       avoid statistically unreliable rankings. The analysis adds the business
                       narrative — which corridors to investigate, not just which corridors are
                       ranked highest."
*/

-- Top 15 worst corridors by average delay days
SELECT
    delay_rank,
    corridor,
    origin_state,
    destination_state,
    order_count,
    avg_delay_days,
    avg_actual_delivery_days,
    avg_estimated_delivery_days,
    late_pct,
    avg_freight_value
FROM {{ ref('mart_delivery_analysis') }}
ORDER BY delay_rank ASC
LIMIT 15;

-- Corridor volume vs delay: are high-volume corridors worse or better?
SELECT
    CASE
        WHEN order_count >= 500  THEN 'High volume (500+)'
        WHEN order_count >= 100  THEN 'Mid volume (100-499)'
        ELSE 'Low volume (10-99)'
    END                                         AS volume_bucket,
    COUNT(*)                                    AS corridor_count,
    ROUND(AVG(avg_delay_days), 1)               AS avg_delay_days,
    ROUND(AVG(late_pct), 1)                     AS avg_late_pct
FROM {{ ref('mart_delivery_analysis') }}
GROUP BY 1
ORDER BY avg_delay_days DESC;