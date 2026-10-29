WITH customer_summary AS (
  SELECT calendar_month, sum(paying) AS paying_customers,
         sum(net_revenue) AS net_revenue, sum(variable_cost) AS variable_cost,
         sum(contribution) AS contribution
  FROM customer_month
  WHERE cohort_month=DATE '2024-01-01' AND age_month IN (0,1)
  GROUP BY calendar_month
), cohort_people AS (
  SELECT DISTINCT person_id FROM customer_month WHERE cohort_month=DATE '2024-01-01'
), ledger_summary AS (
  SELECT date_trunc('month', t.occurred_at::TIMESTAMP)::DATE AS calendar_month,
         sum(t.gross_amount-t.discount_amount-t.refund_amount) AS ledger_net_revenue,
         sum(t.variable_cost) AS ledger_variable_cost
  FROM raw.transactions t JOIN cohort_people p USING(person_id)
  GROUP BY calendar_month
)
SELECT c.calendar_month, c.paying_customers, c.net_revenue,
       round(c.net_revenue/nullif(c.paying_customers,0),2) AS net_revenue_per_payer,
       c.variable_cost, c.contribution,
       c.net_revenue-l.ledger_net_revenue AS revenue_reconciliation_gap,
       c.variable_cost-l.ledger_variable_cost AS cost_reconciliation_gap,
       c.contribution-(l.ledger_net_revenue-l.ledger_variable_cost) AS contribution_reconciliation_gap
FROM customer_summary c JOIN ledger_summary l USING(calendar_month)
ORDER BY c.calendar_month;
