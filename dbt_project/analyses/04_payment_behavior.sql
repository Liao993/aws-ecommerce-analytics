/*
  Analysis: Payment Behavior
  ===========================
  Business Question : Does the number of payment installments predict basket size,
                      and is there an inflection point where more installments correlate
                      with meaningfully higher average order value?

  SQL Pattern       : Filter on dimension_type from UNION ALL mart; ORDER BY installment
                      bucket to surface the inflection point

  Tables Used       : dev_marts.mart_payment_behavior

  Finding           : A clear AOV gradient exists across installment buckets: single-payment
                      orders average R$121, rising to R$185 for 4–6 installments, R$339
                      for 7–12, and R$419 for 13+ installments — a 3.4x difference between
                      cash and maximum-installment buyers. Credit card is the dominant
                      payment method (76,505 orders, 76% of volume) with the highest AOV
                      at R$167, while boleto (R$145), debit card (R$143), and voucher
                      (R$141) are clustered closely together. The 3 "not_defined" payment
                      type orders show 100% cancellation rate, confirming these are
                      incomplete or system-error transactions rather than real payment events.

  So What           : Installment availability is the clearest lever for increasing basket
                      size on this platform. The 7–12 installment bucket drives 3x higher
                      AOV than single-payment, suggesting customers who want higher-value
                      items are credit-constrained and rely on installment plans to make
                      the purchase. Olist should prioritise promoting instalment options
                      at checkout for high-value categories (electronics, furniture) and
                      consider expanding instalment availability to debit card holders,
                      who currently cluster at the lowest AOV tier despite being active buyers.
                      
  Interview Angle   : "The mart uses a UNION ALL pattern to expose two grains
                       (installment_bucket and payment_type) in one table. The analysis
                       filters by dimension_type to isolate the grain it needs —
                       a clean way to avoid two separate mart models for closely related questions."
*/

-- Installment bucket analysis: AOV and cancellation rate by bucket
SELECT
    dimension_value                                         AS installment_bucket,
    order_count,
    avg_order_value,
    total_revenue,
    avg_review_score,
    cancellation_rate_pct
FROM {{ ref('mart_payment_behavior') }}
WHERE dimension_type = 'installment_bucket'
ORDER BY
    CASE dimension_value
        WHEN '1 (cash/single)' THEN 1
        WHEN '2-3'             THEN 2
        WHEN '4-6'             THEN 3
        WHEN '7-12'            THEN 4
        WHEN '13+'             THEN 5
    END;

-- Payment type analysis: which method has the highest cancellation rate?
SELECT
    dimension_value                                         AS payment_type,
    order_count,
    avg_order_value,
    avg_review_score,
    cancellation_rate_pct
FROM {{ ref('mart_payment_behavior') }}
WHERE dimension_type = 'payment_type'
ORDER BY avg_order_value DESC;