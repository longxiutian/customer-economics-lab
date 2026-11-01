-- Ordinary joins and reproducible accounting. Source views and lab_settings are
-- established by 00_sources.sql. Never join raw spending onto transaction rows.

CREATE OR REPLACE VIEW campaign_metadata AS
SELECT campaign_id, min(channel) AS channel, min(target_need) AS target_need
FROM campaign_spend GROUP BY campaign_id;

CREATE OR REPLACE VIEW first_paid AS
SELECT person_id, transaction_id, occurred_at
FROM transactions
WHERE transaction_type = 'payment' AND gross_amount - discount_amount > 0
QUALIFY row_number() OVER (PARTITION BY person_id ORDER BY occurred_at, transaction_id) = 1;

CREATE OR REPLACE VIEW acquired_customers AS
SELECT f.person_id, CAST(date_trunc('month', f.occurred_at) AS DATE) AS cohort_month,
       date_diff('month', DATE '2024-01-01', date_trunc('month', f.occurred_at))::INTEGER AS cohort_index,
       coalesce(c.channel, a.source_type) AS channel, p.primary_need, p.age_band, p.region,
       f.occurred_at AS first_paid_at
FROM first_paid f JOIN people p USING (person_id)
JOIN acquisition_attribution a USING (person_id)
LEFT JOIN campaign_metadata c ON c.campaign_id = a.credited_campaign_id;

CREATE OR REPLACE VIEW financial_person_month AS
SELECT person_id, CAST(date_trunc('month', occurred_at) AS DATE) AS calendar_month,
       count(*) FILTER (WHERE transaction_type = 'payment')::INTEGER AS payment_events,
       count(DISTINCT order_id) FILTER (WHERE transaction_type = 'payment')::INTEGER AS orders,
       sum(CASE WHEN transaction_type = 'payment' THEN gross_amount - discount_amount ELSE 0 END)::DECIMAL(18,2) AS gross_payment_revenue,
       sum(gross_amount - discount_amount - refund_amount)::DECIMAL(18,2) AS net_revenue,
       sum(variable_cost)::DECIMAL(18,2) AS variable_cost,
       sum(gross_amount - discount_amount - refund_amount - variable_cost)::DECIMAL(18,2) AS contribution
FROM transactions GROUP BY person_id, calendar_month;

CREATE OR REPLACE VIEW subscription_person_month AS
SELECT person_id, CAST(date_trunc('month', period_start) AS DATE) AS calendar_month,
       max(CASE WHEN renewal_outcome = 'paid' THEN 1 ELSE 0 END)::INTEGER AS retained
FROM subscription_periods
WHERE renewal_due_at < (SELECT data_as_of FROM lab_settings)
GROUP BY person_id, calendar_month;

CREATE OR REPLACE VIEW customer_month AS
SELECT a.person_id, a.cohort_month, a.cohort_index,
       date_diff('month', a.cohort_month, m.calendar_month)::INTEGER AS age_month,
       m.calendar_month::DATE AS calendar_month, a.channel, a.primary_need, a.age_band,
       coalesce(s.retained, 0)::INTEGER AS retained,
       CASE WHEN coalesce(f.payment_events, 0) > 0 THEN 1 ELSE 0 END::INTEGER AS paying,
       coalesce(f.orders, 0)::INTEGER AS orders,
       coalesce(f.net_revenue, 0)::DECIMAL(18,2) AS net_revenue,
       coalesce(f.variable_cost, 0)::DECIMAL(18,2) AS variable_cost,
       coalesce(f.contribution, 0)::DECIMAL(18,2) AS contribution,
       coalesce(f.gross_payment_revenue, 0)::DECIMAL(18,2) AS gross_payment_revenue
FROM acquired_customers a
CROSS JOIN LATERAL generate_series(a.cohort_month,
    CAST(date_trunc('month', (SELECT data_as_of FROM lab_settings)) - INTERVAL '1 month' AS DATE),
    INTERVAL '1 month') m(calendar_month)
LEFT JOIN subscription_person_month s ON s.person_id = a.person_id AND s.calendar_month = m.calendar_month
LEFT JOIN financial_person_month f ON f.person_id = a.person_id AND f.calendar_month = m.calendar_month;

CREATE OR REPLACE VIEW cohort_age_summary AS
SELECT cohort_month, cohort_index, age_month, calendar_month, channel, primary_need,
       count(*)::INTEGER AS n_acquired, sum(retained)::INTEGER AS n_retained,
       sum(paying)::INTEGER AS n_paying, sum(orders)::INTEGER AS orders,
       sum(gross_payment_revenue)::DECIMAL(18,2) AS gross_payment_revenue,
       sum(net_revenue)::DECIMAL(18,2) AS net_revenue,
       sum(variable_cost)::DECIMAL(18,2) AS variable_cost,
       sum(contribution)::DECIMAL(18,2) AS contribution
FROM customer_month GROUP BY cohort_month, cohort_index, age_month, calendar_month, channel, primary_need;

CREATE OR REPLACE VIEW targeted_spend AS
SELECT CAST(date_trunc('month', spend_date) AS DATE) AS cohort_month, channel, target_need AS primary_need,
       sum(media_spend + other_acquisition_spend)::DECIMAL(18,2) AS acquisition_spend
FROM campaign_spend WHERE target_need IS NOT NULL GROUP BY cohort_month, channel, primary_need;

CREATE OR REPLACE VIEW cohort_acquisition_costs AS
WITH counts AS (
 SELECT cohort_month, channel, primary_need, count(*)::INTEGER AS n_acquired
 FROM acquired_customers GROUP BY cohort_month, channel, primary_need
)
SELECT coalesce(n.cohort_month, s.cohort_month) AS cohort_month,
       coalesce(n.channel, s.channel) AS channel, coalesce(n.primary_need, s.primary_need) AS primary_need,
       coalesce(n.n_acquired, 0)::INTEGER AS n_acquired, s.acquisition_spend,
       s.acquisition_spend / nullif(n.n_acquired, 0) AS cac
FROM counts n FULL OUTER JOIN targeted_spend s USING (cohort_month, channel, primary_need);

CREATE OR REPLACE VIEW monthly_spend AS
SELECT CAST(date_trunc('month', spend_date) AS DATE) AS calendar_month,
       sum(media_spend + other_acquisition_spend)::DECIMAL(18,2) AS acquisition_spend
FROM campaign_spend GROUP BY calendar_month;

CREATE OR REPLACE VIEW company_month AS
WITH layers AS (
 SELECT calendar_month, cohort_month, sum(n_retained)::INTEGER AS n_retained,
        sum(net_revenue)::DECIMAL(18,2) AS net_revenue,
        sum(contribution)::DECIMAL(18,2) AS contribution
 FROM cohort_age_summary GROUP BY calendar_month, cohort_month
)
SELECT l.*, CASE WHEN l.cohort_month = l.calendar_month THEN coalesce(s.acquisition_spend, 0)
                ELSE 0 END::DECIMAL(18,2) AS acquisition_spend
FROM layers l LEFT JOIN monthly_spend s USING (calendar_month);

CREATE OR REPLACE VIEW company_totals AS
SELECT calendar_month, sum(n_retained)::INTEGER AS n_retained,
       sum(net_revenue)::DECIMAL(18,2) AS net_revenue,
       sum(contribution)::DECIMAL(18,2) AS contribution,
       sum(acquisition_spend)::DECIMAL(18,2) AS acquisition_spend
FROM company_month GROUP BY calendar_month;

CREATE OR REPLACE VIEW segmentation_subjects AS
WITH six_month_people AS (
 SELECT c.person_id, a.cohort_month, a.channel, a.primary_need, a.age_band, a.region,
        sum(c.contribution)::DOUBLE AS six_month_contribution,
        max(CASE WHEN c.age_month=5 THEN c.retained ELSE 0 END)::INTEGER AS retained_at_age5
 FROM customer_month c JOIN acquired_customers a USING (person_id)
 WHERE c.age_month < 6 AND a.cohort_month + INTERVAL '6 months' <= (SELECT data_as_of FROM lab_settings)
   AND a.channel IN ('search','partner')
 GROUP BY c.person_id, a.cohort_month, a.channel, a.primary_need, a.age_band, a.region
 HAVING count(*) = 6
)
SELECT *, six_month_contribution - avg(six_month_contribution) OVER (PARTITION BY cohort_month) AS cohort_centered_contribution
FROM six_month_people;

CREATE OR REPLACE VIEW segmentation_profile AS
WITH labeled AS (
 SELECT *, 'primary_need' AS scheme, primary_need AS segment FROM segmentation_subjects
 UNION ALL
 SELECT *, 'age_band', age_band FROM segmentation_subjects
 UNION ALL
 SELECT *, 'region', region FROM segmentation_subjects
 UNION ALL
 SELECT *, 'acquisition_channel', channel FROM segmentation_subjects
)
SELECT scheme, segment, count(*)::INTEGER AS n,
       avg(six_month_contribution) AS mean_contribution,
       var_pop(six_month_contribution) AS variance,
       avg(retained_at_age5) AS retained_share,
       var_pop(cohort_centered_contribution) AS cohort_centered_variance
FROM labeled GROUP BY scheme, segment;

CREATE OR REPLACE VIEW segmentation_comparison AS
WITH overall AS (
 SELECT var_pop(six_month_contribution) AS pooled_variance,
        var_pop(cohort_centered_contribution) AS pooled_cohort_centered_variance
 FROM segmentation_subjects
), grouped AS (
 SELECT scheme, sum(n*variance)/sum(n) AS weighted_within_variance,
        sum(n*cohort_centered_variance)/sum(n) AS cohort_centered_within_variance,
        sum(n)::INTEGER AS n_customers, count(*)::INTEGER AS n_groups, min(n)::INTEGER AS min_group_size
 FROM segmentation_profile GROUP BY scheme
)
SELECT *, 1-weighted_within_variance/nullif(pooled_variance,0) AS variance_reduction,
       1-cohort_centered_within_variance/nullif(pooled_cohort_centered_variance,0) AS cohort_centered_variance_reduction
FROM grouped CROSS JOIN overall;

CREATE OR REPLACE VIEW cohort_totals AS
WITH totals AS (
 SELECT cohort_month, cohort_index, age_month, calendar_month,
        sum(n_acquired)::INTEGER AS n_acquired, sum(n_retained)::INTEGER AS n_retained,
        sum(n_paying)::INTEGER AS n_paying, sum(orders)::INTEGER AS orders,
        sum(gross_payment_revenue)::DECIMAL(18,2) AS gross_payment_revenue,
        sum(net_revenue)::DECIMAL(18,2) AS net_revenue,
        sum(variable_cost)::DECIMAL(18,2) AS variable_cost,
        sum(contribution)::DECIMAL(18,2) AS contribution
 FROM cohort_age_summary GROUP BY cohort_month, cohort_index, age_month, calendar_month
)
SELECT *, n_retained::DOUBLE/n_acquired AS retained_share, n_paying::DOUBLE/n_acquired AS paying_share,
       net_revenue/nullif(first_value(net_revenue) OVER (PARTITION BY cohort_month ORDER BY age_month), 0) AS revenue_retention,
       net_revenue/nullif(n_paying, 0) AS revenue_per_paying_customer,
       net_revenue/n_acquired AS revenue_per_acquired_customer
FROM totals;

CREATE OR REPLACE VIEW cohort_cash_economics AS
WITH cumulative AS (
 SELECT t.cohort_month, t.cohort_index, t.age_month, t.calendar_month, t.n_acquired,
        coalesce(s.acquisition_spend, 0)::DECIMAL(18,2) AS acquisition_spend,
        coalesce(s.acquisition_spend, 0)/t.n_acquired AS cac,
        sum(t.contribution) OVER (PARTITION BY t.cohort_month ORDER BY t.age_month
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)::DECIMAL(18,2) AS cumulative_contribution,
        count(*) OVER (PARTITION BY t.cohort_month)::INTEGER AS observed_months
 FROM cohort_totals t LEFT JOIN monthly_spend s ON s.calendar_month = t.cohort_month
), balances AS (
 SELECT *, cumulative_contribution/n_acquired AS cumulative_contribution_per_customer,
        (cumulative_contribution-acquisition_spend)::DECIMAL(18,2) AS balance_after_acquisition,
        (cumulative_contribution-acquisition_spend)/n_acquired AS balance_per_customer
 FROM cumulative
), payback AS (
 SELECT *, min(CASE WHEN balance_after_acquisition >= 0 THEN age_month END)
             OVER (PARTITION BY cohort_month)::INTEGER AS first_observed_payback_age
 FROM balances
)
SELECT cohort_month, cohort_index, age_month, calendar_month, n_acquired, acquisition_spend, cac,
       cumulative_contribution, cumulative_contribution_per_customer,
       balance_after_acquisition, balance_per_customer, first_observed_payback_age,
       first_observed_payback_age+1 AS cash_payback_month, observed_months
FROM payback;

CREATE OR REPLACE VIEW cohort_six_month_comparison AS
SELECT t.*, c.acquisition_spend, c.cac, c.cumulative_contribution,
       c.cumulative_contribution_per_customer, c.balance_after_acquisition, c.balance_per_customer,
       c.first_observed_payback_age, c.cash_payback_month
FROM cohort_totals t JOIN cohort_cash_economics c USING (cohort_month, cohort_index, age_month, calendar_month, n_acquired)
WHERE t.age_month = 5;

-- Acquisition-only pilot evidence is deliberately separate from customer history.
CREATE OR REPLACE VIEW channel_cac AS
WITH paired AS (
 SELECT t.test_id,t.channel,t.primary_need,t.assigned_at,t.followup_end_at,
        date_diff('day',t.assigned_at,t.followup_end_at)::INTEGER AS followup_days,
        CAST(date_trunc('month',t.assigned_at) AS DATE) AS test_month,
        t.n_assigned AS n_treatment,c.n_assigned AS n_control,
        t.n_buyers AS buyers_treatment,c.n_buyers AS buyers_control,
        t.n_assigned::DOUBLE/c.n_assigned AS scale_to_treatment,
        (t.media_spend+t.other_acquisition_spend)::DECIMAL(18,2) AS spend_treatment,
        (c.media_spend+c.other_acquisition_spend)::DECIMAL(18,2) AS spend_control,
        t.n_buyers::DOUBLE/t.n_assigned AS purchase_rate_treatment,
        c.n_buyers::DOUBLE/c.n_assigned AS purchase_rate_control
 FROM channel_holdouts t JOIN channel_holdouts c USING(test_id,channel,primary_need,assigned_at,followup_end_at)
 WHERE t.arm='treatment' AND c.arm='control'
), lift AS (
 SELECT *,scale_to_treatment*buyers_control AS expected_background_buyers,
        buyers_treatment-scale_to_treatment*buyers_control AS incremental_buyers,
        spend_treatment-scale_to_treatment*spend_control AS incremental_spend,
        n_treatment*sqrt(purchase_rate_treatment*(1-purchase_rate_treatment)/n_treatment
          +purchase_rate_control*(1-purchase_rate_control)/n_control) AS incremental_buyers_se
 FROM paired
), intervals AS (
 SELECT *,incremental_buyers-1.96*incremental_buyers_se AS buyers_ci_lower,
        incremental_buyers+1.96*incremental_buyers_se AS buyers_ci_upper
 FROM lift
)
SELECT *,spend_treatment/nullif(buyers_treatment,0) AS credited_cac,
       CASE WHEN incremental_buyers>0 THEN incremental_spend/incremental_buyers END AS icac,
       CASE WHEN buyers_ci_upper>0 THEN incremental_spend/buyers_ci_upper END AS icac_ci_lower,
       CASE WHEN buyers_ci_lower>0 THEN incremental_spend/buyers_ci_lower END AS icac_ci_upper
FROM intervals;

-- The export contains only complete, fixed-window tests validated against the cutoff.
-- Update each cell from its latest result, even if lift is weak or unfavorable.
CREATE OR REPLACE VIEW channel_cac_current AS
SELECT * FROM channel_cac
QUALIFY row_number() OVER (
    PARTITION BY channel,primary_need ORDER BY followup_end_at DESC,test_id
) = 1;
