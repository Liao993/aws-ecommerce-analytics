/*
  Analysis: Customer Cohort Retention
  =====================================
  Business Question : What percentage of customers in each acquisition cohort made a
                      repeat purchase within 30, 60, and 90 days?

  SQL Pattern       : GROUP BY DATE_TRUNC cohort month; AVG on binary flags;
                      HAVING to filter cohorts with enough customers to be meaningful

  Tables Used       : dev_marts.mart_customer_cohorts

  Finding           : Across all cohorts from 2016-10 to 2018-08 (94,990 customers
                      total), repeat purchase rates within 30, 60, and 90 days are
                      effectively 0% across every cohort month. The largest cohort
                      (2017-11, 7,190 customers) shows the same pattern. This is a
                      known structural characteristic of the Olist dataset — the
                      platform's customer base is almost entirely one-time buyers,
                      with customer_unique_id rarely appearing across more than one
                      order in the 2016–2018 period.

  So What           : The near-zero repeat rate is the most important business insight
                      in this dataset. Olist's revenue growth during 2016–2018 was
                      driven entirely by customer acquisition, not retention. This means
                      CAC (customer acquisition cost) is the dominant cost driver, and
                      any retention or loyalty programme — even one that moved the 30-day
                      repeat rate from 0% to 5% — would represent a structural improvement
                      to unit economics. The business case for a post-purchase email
                      sequence or loyalty incentive is extremely strong given this baseline.
                      
  Interview Angle   : "Cohort analysis requires DATE_TRUNC to group by acquisition month,
                       not individual dates. I used binary flags (repeat_within_30d) in the mart
                       so the analysis just AVGs them — no complex conditional logic in the
                       analysis layer. The finding here — near-zero retention — is itself the
                       insight. It tells you this platform was in pure acquisition mode,
                       which has direct implications for how you'd evaluate its unit economics."
*/

-- Retention rates by acquisition cohort month
SELECT
    cohort_month,
    COUNT(*)                                                AS cohort_size,
    ROUND(AVG(repeat_within_30d) * 100, 1)                 AS retention_30d_pct,
    ROUND(AVG(repeat_within_60d) * 100, 1)                 AS retention_60d_pct,
    ROUND(AVG(repeat_within_90d) * 100, 1)                 AS retention_90d_pct,
    ROUND(AVG(is_repeat_customer) * 100, 1)                AS lifetime_repeat_pct
FROM {{ ref('mart_customer_cohorts') }}
GROUP BY 1
HAVING COUNT(*) >= 50   -- Filter cohorts too small to be meaningful
ORDER BY cohort_month ASC;

-- Overall summary: platform-wide repeat rates
SELECT
    COUNT(*)                                                AS total_customers,
    ROUND(AVG(repeat_within_30d) * 100, 1)                 AS platform_30d_pct,
    ROUND(AVG(repeat_within_60d) * 100, 1)                 AS platform_60d_pct,
    ROUND(AVG(repeat_within_90d) * 100, 1)                 AS platform_90d_pct,
    ROUND(AVG(is_repeat_customer) * 100, 1)                AS platform_lifetime_repeat_pct
FROM {{ ref('mart_customer_cohorts') }};