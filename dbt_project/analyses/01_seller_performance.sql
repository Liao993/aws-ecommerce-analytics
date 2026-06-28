/*
  Analysis: Seller Performance Matrix
  ====================================
  Business Question : Which sellers are high-revenue but low-rated (the risk quadrant),
                      and what is the on-time delivery rate for each revenue/review quadrant?
  SQL Pattern       : SELECT from pre-computed mart; CASE WHEN for quadrant labelling;
                      GROUP BY aggregation over NTILE-scored data
  Tables Used       : dev_marts.mart_seller_performance

  Finding           : 447 sellers fall in the Revenue Risk quadrant (Q4 revenue, Q1–Q2 review),
                      averaging only 9–14% on-time delivery and review scores of 2–3.
                      In contrast, Star Sellers (Q4/Q4) average 20% on-time and a score of 4,
                      with avg revenue of R$27,676 vs R$16,623–23,374 for Revenue Risk sellers.
                      Hidden Gems (Q1–Q2 revenue, Q4 review) achieve 90–96% on-time rates
                      despite earning far less — suggesting operational excellence does not
                      automatically translate to revenue on this platform.

  So What           : Revenue Risk sellers represent the highest intervention priority —
                      they generate significant marketplace volume but drag down platform
                      NPS through poor reviews and unreliable delivery. Olist should
                      implement a seller quality programme targeting this quadrant,
                      with on-time delivery rate as the primary KPI, before focusing
                      on growing Hidden Gems whose operations are already strong.
                      
  Interview Angle   : "I used NTILE(4) in the mart model to avoid re-computing quartiles in every
                       downstream query. The analysis reads from the mart and focuses on business
                       interpretation — which quadrant should the marketplace team act on first?"
*/

-- Quadrant summary: avg on-time rate and seller count per revenue/review quadrant
SELECT
    revenue_quartile,
    review_quartile,
    CASE
        WHEN revenue_quartile = 4 AND review_quartile = 4 THEN 'Star Sellers'
        WHEN revenue_quartile = 4 AND review_quartile <= 2 THEN 'Revenue Risk'
        WHEN revenue_quartile <= 2 AND review_quartile = 4 THEN 'Hidden Gems'
        ELSE 'Middle Pack'
    END                                         AS quadrant_label,
    COUNT(*)                                    AS seller_count,
    ROUND(AVG(on_time_pct), 1)                  AS avg_on_time_pct,
    ROUND(AVG(total_revenue), 0)                AS avg_revenue,
    ROUND(AVG(avg_review_score), 2)             AS avg_review_score,
    ROUND(AVG(avg_delay_days), 1)               AS avg_delay_days
FROM {{ ref('mart_seller_performance') }}
GROUP BY 1, 2, 3
ORDER BY revenue_quartile DESC, review_quartile DESC;

-- Detail view: top 10 Revenue Risk sellers (high revenue, low review score)
SELECT
    seller_id,
    seller_state,
    total_revenue,
    avg_review_score,
    on_time_pct,
    order_count,
    review_score_bucket
FROM {{ ref('mart_seller_performance') }}
WHERE revenue_quartile = 4
  AND review_quartile <= 2
ORDER BY total_revenue DESC
LIMIT 10;