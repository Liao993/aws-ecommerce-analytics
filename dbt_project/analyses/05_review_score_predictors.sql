/*
  Analysis: Review Score Predictors
  ===================================
  Business Question : Does delivery delay predict low review scores? Specifically, what
                      percentage of delayed orders receive a review score of 1 or 2?
  SQL Pattern       : JOIN between mart_delivery_analysis (delay by corridor) and
                      mart_category_performance (review scores by category); delay bucket
                      CASE WHEN; GROUP BY aggregation

  Tables Used       : dev_marts.mart_delivery_analysis, dev_marts.mart_category_performance

  Finding           : All 223 corridors fall into the "On time or early" delay bucket
                      (avg -13 days, 9.1% late rate, 109,547 total orders), confirming
                      that Olist's padded delivery estimates prevent any corridor from
                      averaging a positive delay. Delivery delay therefore cannot be tested
                      as a predictor at corridor level using this dataset's estimates.
                      At category level, the lowest-rated categories are furniture_living_room,
                      computers_accessories, audio, fixed_telephony, and bed_bath_table —
                      all averaging a review score of 3. Notably, computers_accessories is
                      both low-rated (score 3) and high-volume (6,530 orders, R$889K revenue),
                      making it the highest-risk category by revenue exposure. The
                      security_and_services category scores 2 but has only 2 orders,
                      making it statistically unreliable.

  So What           : Because all corridors are technically "on time or early" against padded
                      estimates, delivery delay is not a useful predictor at the corridor
                      level with the current estimation methodology. The more actionable signal
                      is at the category level: computers_accessories combines high revenue,
                      high volume, and below-average review scores — a combination that
                      suggests product quality or expectation-setting issues rather than
                      delivery problems. Olist should investigate seller quality within
                      this category specifically, cross-referencing with the Revenue Risk
                      quadrant from Analysis 01 to identify which sellers in
                      computers_accessories are driving the low scores.
                      
  Interview Angle   : "This analysis joins two mart tables on a shared dimension to test a
                       causal hypothesis: does delay cause bad reviews? The finding — that
                       padded delivery estimates make delay unmeasurable at corridor level —
                       is itself analytically valuable. It reveals a data quality issue in
                       the estimation methodology. I'd flag this to the business as a reason
                       to recalibrate delivery estimates before using them as a performance KPI."
*/

-- Delay bucket vs low review rate using mart_delivery_analysis and mart_seller_performance
-- Delivery corridor delay segments
SELECT
    CASE
        WHEN avg_delay_days <= 0   THEN '1. On time or early'
        WHEN avg_delay_days <= 3   THEN '2. 1-3 days late'
        WHEN avg_delay_days <= 7   THEN '3. 4-7 days late'
        WHEN avg_delay_days <= 14  THEN '4. 8-14 days late'
        ELSE                            '5. 15+ days late'
    END                                                     AS delay_bucket,
    COUNT(*)                                                AS corridor_count,
    ROUND(AVG(avg_delay_days), 1)                           AS avg_delay_days,
    ROUND(AVG(late_pct), 1)                                 AS avg_late_pct,
    ROUND(SUM(order_count), 0)                              AS total_orders
FROM {{ ref('mart_delivery_analysis') }}
GROUP BY 1
ORDER BY 1;

-- Category-level review score vs delivery delay: worst categories
SELECT
    category_name_english,
    avg_review_score,
    avg_delay_days,
    order_count,
    total_revenue
FROM {{ ref('mart_category_performance') }}
WHERE avg_review_score IS NOT NULL
ORDER BY avg_review_score ASC
LIMIT 15;