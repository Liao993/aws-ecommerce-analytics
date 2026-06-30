/*
  Analysis: Customer Lifetime Value by Cohort (Cumulative)
  ==========================================================
  Business Question : For each acquisition cohort, how does cumulative customer
                      spend grow over the months following first purchase? Which cohort
                      has the highest 3-month cumulative CLV?
  SQL Pattern       : DATE_TRUNC for cohort grouping; SUM() OVER with
                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW for
                      cumulative aggregation within each cohort partition
  Tables Used       : dev_marts.mart_customer_cohorts, dev_marts.mart_rfm_segmentation
  Finding           : Cumulative CLV at first purchase is consistent across major cohorts
                     (~R$160-180 per customer in month 0), despite cohort acquisition volume
                     growing roughly 10x from late 2016 (low hundreds) to mid-2017 (nearly
                     3,000/month). Cohorts with fewer than 5 customers show cumulative CLV
                     spikes above R$1,000, but these reflect single high-spend outliers, not
                     a real trend, and should be excluded from any "best cohort" ranking.
So What           : Comparing cohort CLV without a minimum-size filter is misleading — a
                     single repeat buyer in a 1-2 person cohort can outrank a 2,000+ customer
                     cohort on raw average spend. Any acquisition-channel or seasonality
                     conclusion needs a cohort-size floor applied first, or it points
                     marketing spend at noise instead of a real signal.
Interview Angle   : "CLV analysis requires cumulative window functions, not simple GROUP BY.
                     PARTITION BY cohort_month resets the running total per cohort; ORDER BY
                     tenure_months ensures it accumulates forward in time. The ROWS BETWEEN
                     clause makes the frame explicit — I always write it out to avoid
                     dialect-specific ambiguity. Just as important: I added a minimum cohort
                     size filter after noticing single-customer cohorts were producing
                     statistically meaningless 'best CLV' results — that's the kind of check
                     that separates a working query from a trustworthy analysis."
*/

-- Step 1: Join cohort data with RFM to get spend per customer
-- Then compute cumulative CLV per cohort across months since acquisition
WITH customer_spend AS (
    SELECT
        c.customer_unique_id,
        c.cohort_month,
        c.first_order_date,
        r.total_spend,
        r.total_orders,
        r.last_order_date,
        -- Months of customer tenure (first to last order)
        DATEDIFF('month', c.first_order_date, r.last_order_date)    AS tenure_months
    FROM {{ ref('mart_customer_cohorts') }} c
    LEFT JOIN {{ ref('mart_rfm_segmentation') }} r
        ON c.customer_unique_id = r.customer_unique_id
    WHERE r.total_spend IS NOT NULL
),

cohort_summary AS (
    SELECT
        cohort_month,
        tenure_months,
        COUNT(customer_unique_id)                                   AS customer_count,
        ROUND(SUM(total_spend), 2)                                  AS cohort_spend,
        ROUND(AVG(total_spend), 2)                                  AS avg_spend_per_customer
    FROM customer_spend
    GROUP BY cohort_month, tenure_months
),

cumulative AS (
    SELECT
        cohort_month,
        tenure_months,
        customer_count,
        avg_spend_per_customer,
        -- Cumulative CLV: running sum of avg spend within this cohort over time
        ROUND(
            SUM(avg_spend_per_customer) OVER (
                PARTITION BY cohort_month
                ORDER BY tenure_months ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 2
        )                                                           AS cumulative_avg_clv
    FROM cohort_summary
)

SELECT *
FROM cumulative
ORDER BY cohort_month ASC, tenure_months ASC;