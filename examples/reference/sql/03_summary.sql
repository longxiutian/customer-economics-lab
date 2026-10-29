SELECT cohort_month,n_acquired,acquisition_spend,cac,observed_months,first_observed_payback_age,cash_payback_month FROM cohort_cash_economics WHERE age_month=0 ORDER BY cohort_month;

SELECT cohort_month,n_acquired,retained_share,revenue_retention,cac,cumulative_contribution_per_customer,balance_per_customer FROM cohort_six_month_comparison ORDER BY cohort_month;

SELECT * FROM experiment_effects ORDER BY experiment_id;

SELECT * FROM segmentation_comparison ORDER BY scheme;
