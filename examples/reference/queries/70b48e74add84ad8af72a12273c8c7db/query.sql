WITH cohort_people AS (
    SELECT person_id
    FROM customer_month
    WHERE cohort_month = DATE '2024-01-01' AND age_month = 0
), ledger AS (
    SELECT CAST(date_trunc('month', t.occurred_at) AS DATE) AS calendar_month,
           SUM(t.gross_amount - t.discount_amount - t.refund_amount) AS net_revenue,
           SUM(t.variable_cost) AS variable_cost,
           SUM(t.gross_amount - t.discount_amount - t.refund_amount - t.variable_cost) AS contribution
    FROM raw.transactions t
    JOIN cohort_people p USING (person_id)
    WHERE t.occurred_at >= TIMESTAMP '2024-01-01 00:00:00'
      AND t.occurred_at < TIMESTAMP '2024-03-01 00:00:00'
    GROUP BY calendar_month
)
SELECT c.cohort_month, c.age_month, c.calendar_month,
       c.n_acquired, c.n_retained, c.n_paying,
       c.net_revenue, c.variable_cost, c.contribution,
       ROUND(c.revenue_per_paying_customer, 2) AS net_revenue_per_payer,
       c.net_revenue - l.net_revenue AS ledger_revenue_gap,
       c.variable_cost - l.variable_cost AS ledger_cost_gap,
       c.contribution - l.contribution AS ledger_contribution_gap
FROM cohort_totals c
JOIN ledger l USING (calendar_month)
WHERE c.cohort_month = DATE '2024-01-01' AND c.age_month IN (0, 1)
ORDER BY c.age_month;
