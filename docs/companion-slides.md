# Companion slides: the report's construction

The main teaching narrative is how the report was created. Use Appendix E as the organizing source: datasets and UCV fields, source relationships, methodological assets, skills, executable analysis, document generation and verification. Business findings supply concrete examples of that process. The current revision is not constrained to twelve slides; allocate space for readability.

End the deck with the following FAQ section. These are prompts students can copy after completing the skill, not claims about work already performed. Keep the model-research prompt as a research-and-evaluation request; do not imply the existing shifted-Beta-Geometric model has no unobserved heterogeneity. Distinguish that retention model from the complete revenue/contribution and acquisition-cost calculation used to obtain LTV.

## FAQ: What Else to Prompt after Running the Skill?

1. **Describe the datasets and their customer information.**

   “Describe every dataset and provide a data dictionary for each. Explain its row unit, keys, links to other tables, and each field's meaning, type, units and missingness. Organize every field using the Universal Customer View: Identifiers, Engagement, Relationship and Perception. Explain ambiguous or contextual classifications and identify information we do not observe.”

2. **Walk through the SQL behind the cohort triangle.**

   “Walk me through the SQL-based process that turns individual-level transactional data into the report's triangular cohort view. Use a few actual customers, show the SQL and small intermediate tables, and explain each step: identify first paid acquisition, assign the acquisition cohort, calculate months since acquisition, build customer-month records, and aggregate cohort outcomes. Show how retention uses subscription records and the original acquired-customer denominator. Then explain how the aggregated results become the displayed triangle, why recent cohorts have fewer observed periods, and why future unobserved cells stay blank while observed months with no activity can be zero. Trace one displayed cell back to its source records.”

3. **Research and test alternative LTV models.**

   “Research other LTV models, emphasizing unobserved heterogeneity within cohorts and/or customer-level LTV estimates. Explain what heterogeneity Longxiu's current shifted-Beta-Geometric model already captures and what each alternative adds. Propose train, validation and holdout splits, justify them, then compare the current approach with suitable alternatives using only information available at each forecast date. Evaluate LTV accuracy, calibration and implications for decisions on a common economic basis.”

4. **Find a more useful segmentation strategy.**

   “Compare alternative segmentations using the available customer attributes. Seek within-cell homogeneity and across-cell heterogeneity in customer economics, comparing strategies at similar complexity. Evaluate held-out performance, segment size, stability and actionability, accounting for cohort differences. Does any strategy improve meaningfully on our current channel-and-need groups, and what different management action would it support?”

5. **Identify what could change the recommendation.**

   “Stress-test the acquisition recommendations against alternative valuation horizons, discount rates, contribution assumptions and iCAC estimates. Allow additional customers' value to differ from the current cohort benchmark. Show which conclusions remain stable, what would reverse the preferred channel or cash-recovery assessment, and which additional evidence would most reduce that uncertainty.”

6. **Adapt the skill to another business.**

   “Using a business description and sample exports I provide, show how to adapt this workflow to another company. Map its data to the required customer information, identify missing inputs, and explain which definitions, models, assets and skill instructions must change. Propose a reproducible implementation and validation plan that preserves the original Studio North case for comparison.”

For the SQL walkthrough, follow `sql/01_views.sql`: `first_paid` → `acquired_customers`; `financial_person_month` and `subscription_person_month` → `customer_month` → `cohort_age_summary` → `cohort_totals`. Explain the customer-month grid and aggregation before joins so multiple transactions do not duplicate customers. The current report pivots the saved SQL aggregates in `cohort_lab/report.py`; show that presentation step accurately rather than claiming the existing SQL produces a wide matrix. Label cohort order and cohort-age axes to explain the triangle's orientation.

When authoring slides, retain all six complete prompts in editable text or speaker notes if their on-slide versions need shortening. Preserve the future-model challenge's separate, instructor-held evaluation boundary. Any implemented extension should save its own source, assumptions, inputs, outputs and checks rather than overwrite the frozen reference.
