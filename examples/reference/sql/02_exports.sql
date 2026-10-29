SELECT * FROM customer_month ORDER BY person_id, age_month;

SELECT * FROM cohort_age_summary ORDER BY cohort_month, channel, primary_need, age_month;

SELECT * FROM cohort_acquisition_costs ORDER BY cohort_month, channel, primary_need;

SELECT * FROM company_month ORDER BY calendar_month, cohort_month;

SELECT * FROM experiment_summary ORDER BY experiment_id, arm;

SELECT * FROM segmentation_comparison ORDER BY scheme;

SELECT * FROM cohort_totals ORDER BY cohort_month, age_month;

SELECT * FROM cohort_cash_economics ORDER BY cohort_month, age_month;

SELECT * FROM company_totals ORDER BY calendar_month;

SELECT * FROM experiment_effects ORDER BY experiment_id;

SELECT * FROM cohort_six_month_comparison ORDER BY cohort_month;

SELECT * FROM cohort_economics_ex_tests ORDER BY cohort_month, age_month;
