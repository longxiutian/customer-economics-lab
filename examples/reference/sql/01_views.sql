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

CREATE OR REPLACE VIEW experiment_person AS
SELECT e.experiment_id, e.person_id, e.tested_campaign_id, e.arm,
       e.assigned_at, e.followup_end_at, c.channel, c.target_need AS primary_need,
       max(CASE WHEN t.transaction_type = 'payment' THEN 1 ELSE 0 END)::INTEGER AS buyer,
       coalesce(sum(t.gross_amount - t.discount_amount - t.refund_amount), 0)::DECIMAL(18,2) AS net_revenue,
       coalesce(sum(t.gross_amount - t.discount_amount - t.refund_amount - t.variable_cost), 0)::DECIMAL(18,2) AS contribution
FROM experiment_assignments e JOIN campaign_metadata c ON c.campaign_id = e.tested_campaign_id
LEFT JOIN transactions t ON t.person_id = e.person_id AND t.occurred_at >= e.assigned_at AND t.occurred_at < e.followup_end_at
GROUP BY e.experiment_id, e.person_id, e.tested_campaign_id, e.arm,
         e.assigned_at, e.followup_end_at, c.channel, c.target_need;

CREATE OR REPLACE VIEW experiment_spend AS
WITH designs AS (
 SELECT DISTINCT experiment_id, tested_campaign_id, assigned_at, followup_end_at FROM experiment_assignments
)
SELECT d.experiment_id, sum(s.media_spend)::DECIMAL(18,2) AS media_spend
FROM designs d JOIN campaign_spend s ON s.campaign_id = d.tested_campaign_id
AND s.spend_date >= CAST(d.assigned_at AS DATE) AND s.spend_date < CAST(d.followup_end_at AS DATE)
GROUP BY d.experiment_id;

CREATE OR REPLACE VIEW experiment_summary AS
SELECT e.experiment_id, e.channel, e.primary_need, e.arm, count(*)::INTEGER AS n_assigned,
       sum(e.buyer)::INTEGER AS n_buyers, sum(e.net_revenue)::DECIMAL(18,2) AS net_revenue,
       sum(e.contribution)::DECIMAL(18,2) AS contribution,
       CASE WHEN e.arm = 'treatment' THEN max(s.media_spend) ELSE 0 END::DECIMAL(18,2) AS media_spend,
       min(e.assigned_at) AS assigned_at, max(e.followup_end_at) AS followup_end_at,
       epoch(max(e.followup_end_at) - min(e.assigned_at))/86400.0 AS followup_days,
       var_samp(e.contribution::DOUBLE) AS contribution_sample_variance
FROM experiment_person e JOIN experiment_spend s USING (experiment_id)
GROUP BY e.experiment_id, e.channel, e.primary_need, e.arm;

CREATE OR REPLACE VIEW experiment_effects AS
WITH paired AS (
 SELECT t.experiment_id, t.channel, t.primary_need, t.n_assigned AS n_treatment, c.n_assigned AS n_control,
        t.assigned_at, t.followup_end_at, t.followup_days,
        t.n_buyers AS buyers_treatment, c.n_buyers AS buyers_control,
        t.n_buyers::DOUBLE/t.n_assigned AS purchase_rate_treatment,
        c.n_buyers::DOUBLE/c.n_assigned AS purchase_rate_control,
        t.n_buyers - c.n_buyers * t.n_assigned::DOUBLE/c.n_assigned AS incremental_buyers,
        t.net_revenue - c.net_revenue * t.n_assigned::DOUBLE/c.n_assigned AS incremental_net_revenue,
        t.contribution - c.contribution * t.n_assigned::DOUBLE/c.n_assigned AS incremental_contribution,
        t.media_spend - c.media_spend * t.n_assigned::DOUBLE/c.n_assigned AS incremental_media_spend,
        sqrt(t.contribution_sample_variance/t.n_assigned
           + c.contribution_sample_variance/c.n_assigned) AS contribution_difference_per_prospect_se
 FROM experiment_summary t JOIN experiment_summary c USING (experiment_id, channel, primary_need)
 WHERE t.arm = 'treatment' AND c.arm = 'control'
), effects AS (
 SELECT *, purchase_rate_treatment - purchase_rate_control AS purchase_rate_difference,
        sqrt(purchase_rate_treatment*(1-purchase_rate_treatment)/n_treatment
           + purchase_rate_control*(1-purchase_rate_control)/n_control) AS purchase_rate_difference_se
 FROM paired
)
SELECT experiment_id, channel, primary_need, n_treatment, n_control, buyers_treatment, buyers_control,
       assigned_at, followup_end_at, followup_days,
       purchase_rate_treatment, purchase_rate_control, purchase_rate_difference, purchase_rate_difference_se,
       greatest(-1.0, purchase_rate_difference - 1.96*purchase_rate_difference_se) AS purchase_rate_ci_lower,
       least(1.0, purchase_rate_difference + 1.96*purchase_rate_difference_se) AS purchase_rate_ci_upper,
       incremental_buyers, incremental_net_revenue, incremental_contribution, incremental_media_spend,
       incremental_contribution - incremental_media_spend AS incremental_contribution_after_media,
       (incremental_contribution - incremental_media_spend)/n_treatment AS incremental_contribution_after_media_per_prospect,
       contribution_difference_per_prospect_se AS incremental_contribution_after_media_per_prospect_se,
       (incremental_contribution - incremental_media_spend)/n_treatment
           - 1.96*contribution_difference_per_prospect_se AS incremental_contribution_after_media_per_prospect_ci_lower,
       (incremental_contribution - incremental_media_spend)/n_treatment
           + 1.96*contribution_difference_per_prospect_se AS incremental_contribution_after_media_per_prospect_ci_upper,
       n_treatment*contribution_difference_per_prospect_se AS incremental_contribution_after_media_se,
       incremental_contribution - incremental_media_spend
           - 1.96*n_treatment*contribution_difference_per_prospect_se AS incremental_contribution_after_media_ci_lower,
       incremental_contribution - incremental_media_spend
           + 1.96*n_treatment*contribution_difference_per_prospect_se AS incremental_contribution_after_media_ci_upper,
       CASE WHEN incremental_buyers > 0 THEN incremental_media_spend/incremental_buyers END AS incremental_cac,
       incremental_net_revenue/nullif(incremental_media_spend, 0) AS iroas
FROM effects;

CREATE OR REPLACE VIEW segmentation_comparison AS
WITH six_month_people AS (
 SELECT c.person_id, a.primary_need, a.age_band, a.region,
        sum(c.contribution)::DOUBLE AS six_month_contribution
 FROM customer_month c JOIN acquired_customers a USING (person_id)
 WHERE c.age_month < 6 AND a.cohort_month + INTERVAL '6 months' <= (SELECT data_as_of FROM lab_settings)
 GROUP BY c.person_id, a.primary_need, a.age_band, a.region
 HAVING count(*) = 6
), grouped AS (
 SELECT 'primary_need' AS scheme, primary_need AS segment, count(*) AS n, var_pop(six_month_contribution) AS variance
 FROM six_month_people GROUP BY primary_need
 UNION ALL
 SELECT 'age_band', age_band, count(*), var_pop(six_month_contribution) FROM six_month_people GROUP BY age_band
 UNION ALL
 SELECT 'region', region, count(*), var_pop(six_month_contribution) FROM six_month_people GROUP BY region
)
SELECT scheme, sum(n*variance)/sum(n) AS weighted_within_variance,
       sum(n)::INTEGER AS n_customers, count(*)::INTEGER AS n_groups, min(n)::INTEGER AS min_group_size
FROM grouped GROUP BY scheme;

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
