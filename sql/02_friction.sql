-- Post-acquisition diagnostics, separate from the baseline forecasting features.
-- A fixed 27-day window includes the onboarding response and precedes every
-- first renewal in this release. No eventual renewal/exit determines a group.
-- Materialize the small person-level tables to avoid repeatedly scanning CSVs.
CREATE OR REPLACE TEMP TABLE friction_population AS
SELECT a.*, first_paid_at + INTERVAL '27 days' AS landmark_at,
       first_paid_at + INTERVAL '27 days' <= (SELECT data_as_of FROM lab_settings) AS exposure_complete,
       cohort_month + INTERVAL '6 months' <= (SELECT data_as_of FROM lab_settings) AS age5_observed
FROM acquired_customers a
WHERE channel IN ('search','partner')
  AND NOT EXISTS (SELECT 1 FROM experiment_assignments x WHERE x.person_id=a.person_id);

CREATE OR REPLACE TEMP TABLE friction_subjects AS
WITH events AS (
 SELECT a.person_id,
        count(*) FILTER (WHERE e.event_type='onboarding_completed') AS onboarding_completions,
        count(*) FILTER (WHERE e.event_type='core_action') AS early_core_actions,
        count(*) FILTER (WHERE e.event_type='support_contact') AS early_support_contacts,
        max(e.occurred_at) AS latest_feature_event_at
 FROM friction_population a LEFT JOIN product_events e
   ON e.person_id=a.person_id AND e.occurred_at>=a.first_paid_at AND e.occurred_at<a.landmark_at
 GROUP BY a.person_id
), responses AS (
 SELECT a.person_id,f.response_id,f.submitted_at,f.ease_rating,f.value_rating,f.main_difficulty
 FROM friction_population a JOIN feedback f
   ON f.person_id=a.person_id AND f.submitted_at>=a.first_paid_at AND f.submitted_at<a.landmark_at
 WHERE f.journey_stage='onboarding'
 QUALIFY row_number() OVER (PARTITION BY a.person_id ORDER BY f.submitted_at,f.response_id)=1
), renewals AS (
 SELECT a.person_id,s.renewal_due_at AS first_renewal_due_at,s.renewal_outcome,
        CASE WHEN s.renewal_due_at<(SELECT data_as_of FROM lab_settings)
                   AND s.renewal_outcome<>'pending'
             THEN (s.renewal_outcome='paid')::INTEGER END AS retained_age1
 FROM friction_population a LEFT JOIN subscription_periods s
   ON s.person_id=a.person_id AND s.renewal_due_at>a.first_paid_at
 QUALIFY row_number() OVER(PARTITION BY a.person_id ORDER BY s.renewal_due_at,s.period_id)=1
), refunds AS (
 SELECT a.person_id,count(t.transaction_id)::INTEGER AS in_window_refunds
 FROM friction_population a LEFT JOIN transactions t ON t.person_id=a.person_id
   AND t.transaction_type='refund' AND t.occurred_at>=a.first_paid_at AND t.occurred_at<a.landmark_at
 GROUP BY a.person_id
), baseline AS (
 SELECT a.person_id,p.plan_tier AS initial_plan,t.discount_amount AS initial_discount,
        m.contribution AS contribution_age0
 FROM friction_population a JOIN first_paid f USING(person_id)
 JOIN transactions t ON t.transaction_id=f.transaction_id
 LEFT JOIN subscription_periods p ON p.period_id=t.period_id
 JOIN customer_month m ON m.person_id=a.person_id AND m.age_month=0
), outcomes AS (
 SELECT m.person_id,max(m.retained) FILTER (WHERE m.age_month=5) AS retained_age5,
        sum(m.contribution) FILTER (WHERE m.age_month BETWEEN 1 AND 5) AS contribution_ages1_5
 FROM customer_month m JOIN friction_population a USING(person_id)
 GROUP BY m.person_id
)
SELECT a.*, e.onboarding_completions,e.early_core_actions,e.early_support_contacts,
       e.latest_feature_event_at,r.response_id,r.submitted_at AS feedback_at,
       r.ease_rating,r.value_rating,r.main_difficulty,
       CASE WHEN r.response_id IS NULL THEN 'no_response'
            WHEN r.main_difficulty IS NULL THEN 'unanswered_item'
            ELSE r.main_difficulty END AS survey_group,
       s.first_renewal_due_at,s.retained_age1,
       b.initial_plan,b.initial_discount,b.contribution_age0,q.in_window_refunds,
       CASE WHEN a.age5_observed THEN o.retained_age5 END AS retained_age5,
       CASE WHEN a.age5_observed THEN o.contribution_ages1_5 END AS contribution_ages1_5
FROM friction_population a JOIN events e USING(person_id)
LEFT JOIN responses r USING(person_id) LEFT JOIN renewals s USING(person_id)
LEFT JOIN baseline b USING(person_id)
LEFT JOIN refunds q USING(person_id)
LEFT JOIN outcomes o USING(person_id)
WHERE a.exposure_complete;

CREATE OR REPLACE VIEW friction_long AS
SELECT *, 'early_use' AS scheme,
       CASE WHEN early_core_actions>0 THEN 'recorded' ELSE 'not_recorded' END AS segment
FROM friction_subjects
UNION ALL
SELECT *, 'onboarding',CASE WHEN onboarding_completions>0 THEN 'recorded' ELSE 'not_recorded' END
FROM friction_subjects
UNION ALL
SELECT *, 'support',CASE WHEN early_support_contacts>0 THEN 'recorded' ELSE 'not_recorded' END
FROM friction_subjects
UNION ALL
SELECT *, 'reported_difficulty',survey_group FROM friction_subjects;

CREATE OR REPLACE VIEW friction_segment_summary AS
SELECT scheme,segment,count(*)::INTEGER AS n_acquired,
       count(retained_age1)::INTEGER AS n_age1_observed,
       sum(retained_age1)::INTEGER AS n_retained_age1,
       avg(retained_age1) AS retained_share_age1,
       count(retained_age5)::INTEGER AS n_age5_observed,
       sum(retained_age5)::INTEGER AS n_retained_age5,
       avg(retained_age5) AS retained_share_age5,
       sum(contribution_ages1_5)::DECIMAL(18,2) AS contribution_ages1_5,
       avg(contribution_ages1_5) AS mean_contribution_ages1_5,
       var_samp(contribution_ages1_5) AS variance_contribution_ages1_5,
       count(response_id)::INTEGER AS n_respondents,
       count(value_rating)::INTEGER AS n_value_ratings,
       avg(value_rating) AS mean_value_rating
FROM friction_long
GROUP BY scheme,segment;

CREATE OR REPLACE VIEW friction_cohort_segments AS
SELECT cohort_month,channel,primary_need,scheme,segment,
       count(*)::INTEGER AS n_acquired,
       count(retained_age1)::INTEGER AS n_age1_observed,
       sum(retained_age1)::INTEGER AS n_retained_age1,
       avg(retained_age1) AS retained_share_age1,
       count(retained_age5)::INTEGER AS n_outcome_observed,
       sum(retained_age5)::INTEGER AS n_retained_age5,
       avg(retained_age5) AS retained_share_age5,
       sum(contribution_ages1_5)::DECIMAL(18,2) AS contribution_ages1_5,
       avg(contribution_ages1_5) AS mean_contribution_ages1_5,
       count(response_id)::INTEGER AS n_respondents
FROM friction_long GROUP BY cohort_month,channel,primary_need,scheme,segment;

CREATE OR REPLACE VIEW friction_cohort_summary AS
SELECT cohort_month,primary_need,count(*)::INTEGER AS n_acquired,
       count(retained_age1)::INTEGER AS n_age1_observed,
       sum(retained_age1)::INTEGER AS n_retained_age1,
       avg(retained_age1) AS retained_share_age1,
       sum((onboarding_completions=0)::INTEGER)::INTEGER AS n_no_completion,
       sum((early_core_actions=0)::INTEGER)::INTEGER AS n_no_core_action,
       sum((early_support_contacts>0)::INTEGER)::INTEGER AS n_support_contact,
       count(response_id)::INTEGER AS n_respondents,
       count(main_difficulty)::INTEGER AS n_difficulty_answers,
       sum((main_difficulty<>'none')::INTEGER)::INTEGER AS n_reported_difficulty,
       count(value_rating)::INTEGER AS n_value_ratings,
       sum((value_rating<=2)::INTEGER)::INTEGER AS n_low_value_rating,
       count(retained_age5)::INTEGER AS n_outcome_observed,
       sum(retained_age5)::INTEGER AS n_retained_age5,
       avg(retained_age5) AS retained_share_age5,
       avg(contribution_ages1_5) AS mean_contribution_ages1_5
FROM friction_subjects GROUP BY cohort_month,primary_need;

CREATE OR REPLACE VIEW friction_matched_comparison AS
SELECT year(cohort_month)::INTEGER AS acquisition_year,channel,primary_need,scheme,segment,
       count(*)::INTEGER AS n_acquired,sum(retained_age5)::INTEGER AS n_retained_age5,
       avg(retained_age5) AS retained_share_age5,
       sum(contribution_ages1_5)::DECIMAL(18,2) AS contribution_ages1_5,
       avg(contribution_ages1_5) AS mean_contribution_ages1_5
FROM friction_long
WHERE month(cohort_month) BETWEEN 1 AND 6 AND age5_observed
GROUP BY acquisition_year,channel,primary_need,scheme,segment;

CREATE OR REPLACE VIEW friction_source_audit AS
SELECT 'product_events' AS source,event_type AS signal,count(*)::INTEGER AS n_records,
       count(*) FILTER(WHERE e.occurred_at<a.first_paid_at)::INTEGER AS n_before_payment,
       count(*) FILTER(WHERE e.occurred_at>=a.first_paid_at AND e.occurred_at<a.first_paid_at+INTERVAL '27 days')::INTEGER AS n_in_window,
       min(epoch(e.occurred_at-a.first_paid_at)/86400.) AS earliest_days_after_payment,
       max(epoch(e.occurred_at-a.first_paid_at)/86400.) AS latest_days_after_payment
FROM product_events e JOIN acquired_customers a USING(person_id) GROUP BY event_type
UNION ALL
SELECT 'feedback',journey_stage,count(*)::INTEGER,
       count(*) FILTER(WHERE f.submitted_at<a.first_paid_at)::INTEGER,
       count(*) FILTER(WHERE f.submitted_at>=a.first_paid_at AND f.submitted_at<a.first_paid_at+INTERVAL '27 days')::INTEGER,
       min(epoch(f.submitted_at-a.first_paid_at)/86400.),max(epoch(f.submitted_at-a.first_paid_at)/86400.)
FROM feedback f JOIN acquired_customers a USING(person_id) GROUP BY journey_stage;

CREATE OR REPLACE VIEW friction_timing_audit AS
SELECT 27 AS exposure_days,
       (SELECT count(*) FROM acquired_customers)::INTEGER AS all_acquired,
       (SELECT count(*) FROM acquired_customers a WHERE EXISTS
          (SELECT 1 FROM experiment_assignments x WHERE x.person_id=a.person_id))::INTEGER AS acquired_experimental,
       (SELECT count(*) FROM acquired_customers a WHERE channel NOT IN ('search','partner') AND NOT EXISTS
          (SELECT 1 FROM experiment_assignments x WHERE x.person_id=a.person_id))::INTEGER AS other_nonexperimental_channels,
       (SELECT count(*) FROM friction_population)::INTEGER AS eligible_paid_non_test,
       (SELECT count(*) FROM friction_population WHERE NOT exposure_complete)::INTEGER AS incomplete_exposure,
       count(*)::INTEGER AS diagnostic_customers,
       count(retained_age1)::INTEGER AS age1_observed_customers,
       sum(age5_observed::INTEGER)::INTEGER AS mature_customers,
       count(*) FILTER(WHERE first_renewal_due_at<landmark_at)::INTEGER AS renewals_before_landmark,
       min(epoch(first_renewal_due_at-first_paid_at)/86400.) AS earliest_renewal_days,
       count(*) FILTER(WHERE latest_feature_event_at>=landmark_at OR feedback_at>=landmark_at)::INTEGER AS feature_window_violations,
       (SELECT count(*) FROM friction_population a JOIN subscription_periods s USING(person_id)
        WHERE s.cancellation_effective_at>=a.first_paid_at AND s.cancellation_effective_at<a.landmark_at)::INTEGER AS in_window_effective_cancellations,
       (SELECT count(*) FROM friction_population a JOIN subscription_periods s USING(person_id)
        WHERE s.period_end>a.first_paid_at AND s.period_end<a.landmark_at)::INTEGER AS in_window_period_ends,
       (SELECT count(*) FROM friction_population a JOIN transactions t USING(person_id)
        WHERE t.transaction_type='refund' AND t.occurred_at>=a.first_paid_at AND t.occurred_at<a.landmark_at)::INTEGER AS in_window_refunds,
       (SELECT count(*) FROM friction_population a JOIN transactions t USING(person_id)
        WHERE date_diff('month',a.cohort_month,t.occurred_at) BETWEEN 1 AND 5
          AND t.occurred_at<a.landmark_at)::INTEGER AS outcome_transactions_before_landmark
FROM friction_subjects;
