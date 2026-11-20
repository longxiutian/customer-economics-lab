# Companion slides: the report's construction

The main teaching narrative is how the report was created. Use Appendix E as the organizing source: datasets and UCV fields, source relationships, methodological assets, skills, executable analysis, document generation and verification. Business findings supply concrete examples of that process. The current revision is not constrained to twelve slides; allocate space for readability.

Explain the three skill roles: the root skill owns the analytical contract; `skills/student-teacher/SKILL.md` teaches it through nineteen visible checkpoints and explicit **next step** gates; the executive-report skill specifies the final document. Show the saved lesson state and one intermediate artifact before the final report. Use `docs/student-workflow.md` for the audited map.

The repository preserves the **archived 33-slide November 3, 2026 edition**: [editable PowerPoint](../teaching/Studio-North-Agentic-AI-Lab.pptx) and [PDF](../teaching/Studio-North-Agentic-AI-Lab.pdf). Its construction narrative uses dataset 5.1 and the course-neutral Version B report. The FAQ section begins on slide 26; the SQL walkthrough is slide 28 and the cohort-oriented four-segment view is slide 29. Preserve the older 13-slide `teaching/customer-economics-lab.*` files and their provenance as the archived 1.7.0 companion.

The current course slides are maintained in the instructor-edited main deck and published on the Canvas Day page. Use the current three-path workflow, explicit end/feedback/debrief sequence and all twelve FAQ prompts below.

End the deck with the following FAQ section. These are prompts students can copy after completing the skill, not claims about work already performed. Keep the model-research prompt as a research-and-evaluation request; do not imply the existing shifted-Beta-Geometric model has no unobserved heterogeneity. Distinguish that retention model from the complete revenue/contribution and acquisition-cost calculation used to obtain LTV.

## FAQ: What Else to Prompt after Running the Skill?

1. **Explain my files and the report architecture.**

   “Explain how my Studio North report is generated from the eight datasets, SKILL.md, reference assets, DuckDB SQL, model fits and figures. First identify my execution route. Show my actual source and output locations, how DuckDB was used, and which files I can download. For BlueChip, use the saved file-map action and distinguish cluster paths from downloads. Use verified records from my own workspace.”

2. **Describe the datasets and their customer information.**

   “Describe every dataset and provide a data dictionary for each. Explain its row unit, keys, links to other tables, and each field's meaning, type, units and missingness. Organize every field using the Universal Customer View: Identifiers, Engagement, Relationship and Perception. Explain ambiguous or contextual classifications and identify information we do not observe.”

3. **Walk through the SQL behind the cohort triangle.**

   “Walk me through the SQL-based process that turns individual-level transactional data into the report's triangular cohort view. Use a few actual customers, show the SQL and small intermediate tables, and explain each step: identify first paid acquisition, assign the acquisition cohort, calculate months since acquisition, build customer-month records, and aggregate cohort outcomes. Show how retention uses subscription records and the original acquired-customer denominator. Then explain how the aggregated results become the displayed triangle, why recent cohorts have fewer observed periods, and why future unobserved cells stay blank while observed months with no activity can be zero. Trace one displayed cell back to its source records.”

4. **Replay the report as a month-by-month dashboard.**

   “Use my attached Studio North executive PDF as the baseline. Build a self-contained dashboard file I can open in a browser and step through one month at a time from January 2024 onward. Get the public data, SQL and code from the course repository. Work in a new project folder. Use matching saved exports if I supplied them.

   For each labeled as-of month, show only what Studio North could have known by that month's end: the retention triangle, each joining cohort's mix across the four channel-by-need segments, and contribution LTV, CAC and payback as the report defines them. Hide later months and cohorts that had not yet joined.

   Mark observed results differently from forecasts. Replay observed results by filtering saved records by date. Refit each forecast with the report's model, using only records dated through the as-of month; never reuse parameters fitted on later data. If history is too short to fit, leave the forecast blank and say so.

   Check that the latest month reproduces the PDF; explain any difference. Then answer: as the months advance, are newer cohorts' economics improving, and in which month did the evidence first support the report's recommendation?

   Follow-up check: rebuild one earlier month from records cut off at that month; the view should not change.”

5. **Compare the four segments within each cohort.**

   “Reorganize the cohort-return charts so each figure represents one acquisition cohort and shows all four channel-by-need segments. Use consistent segment colors, axes and horizons, and distinguish observed returns from forecasts. Keep the underlying calculations unchanged. Explain which segments perform better within each cohort and how those differences evolve across cohorts.”

6. **Research and test alternative LTV models.**

   “Research other LTV models, emphasizing unobserved heterogeneity within cohorts and/or customer-level LTV estimates. Explain what heterogeneity Longxiu's current shifted-Beta-Geometric model already captures and what each alternative adds. Propose train, validation and holdout splits, justify them, then compare the current approach with suitable alternatives using only information available at each forecast date. Evaluate LTV accuracy, calibration and implications for decisions on a common economic basis.”

7. **How does add-on revenue affect our LTV projections?**

   “Stress-test how this run's LTV projections handle optional add-on purchases.

   Trace add-ons from transactions through SQL to the forecasts. Explain what sBG predicts and what the separate revenue model adds. Which features of irregular spending does the current model capture or miss? Do the forecast bands reflect unpredictable future purchases?

   Compare subscription and add-on revenue per retained member at matched customer ages and across segments. Could changing purchase frequency, purchase size, margins, or a relationship between spending and churn weaken the projections?

   Holding retention and CAC fixed, compare lower, baseline and higher future add-on contribution. How do LTV, LTV-to-CAC, payback and our recommendation change? Which additional data or revenue model would improve the analysis? Preserve the baseline report and label each scenario's assumptions.”

8. **Enter the private-holdout model challenge.**

   “Use my attached Studio North executive PDF to identify the baseline. Read the public model-challenge skill and submission contract. Help our team build a separate reproducible model project that forecasts retained members, net revenue and contribution for the existing cohorts through December 2026. Propose chronological validation using only released history. Preserve the standard prediction interface and grid, explain why cohorts are forecast at different customer ages, and prepare the code, lockfile, validation and GitHub commit for submission. Ask before making our work public.”

9. **Find a more useful segmentation strategy.**

   “Compare alternative segmentations using the available customer attributes. Seek within-cell homogeneity and across-cell heterogeneity in customer economics, comparing strategies at similar complexity. Evaluate held-out performance, segment size, stability and actionability, accounting for cohort differences. Does any strategy improve meaningfully on our current channel-and-need groups, and what different management action would it support?”

10. **Identify what could change the recommendation.**

   “Stress-test the acquisition recommendations against alternative valuation horizons, discount rates, contribution assumptions and iCAC estimates. Allow additional customers' value to differ from the current cohort benchmark. Show which conclusions remain stable, what would reverse the preferred channel or cash-recovery assessment, and which additional evidence would most reduce that uncertainty.”

11. **Explain blended CAC and reconcile acquisition-cost measures.**

   “Explain what the report calls observed blended or historical average CAC. Reconcile total tracked acquisition spending and actual acquisitions with channel attributional CAC and current holdout-based iCAC. Explain which measure supports which decision, how organic control inflow enters incrementality, and how CAC should be combined with contribution LTV before acquisition cost. Subtract acquisition cost once and state the assumption about additional customers’ value.”

12. **Adapt the skill to another business.**

   “Using a business description and sample exports I provide, show how to adapt this workflow to another company. Map its data to the required customer information, identify missing inputs, and explain which definitions, models, assets and skill instructions must change. Propose a reproducible implementation and validation plan that preserves the original Studio North case for comparison.”

For the SQL walkthrough, follow `sql/01_views.sql`: `first_paid` → `acquired_customers`; `financial_person_month` and `subscription_person_month` → `customer_month` → `cohort_age_summary` → `cohort_totals`. Explain the customer-month grid and aggregation before joins so multiple transactions do not duplicate customers. The current report pivots the saved SQL aggregates in `cohort_lab/report.py`; show that presentation step accurately rather than claiming the existing SQL produces a wide matrix. Label cohort order and cohort-age axes to explain the triangle's orientation.

For the cohort-oriented chart prompt, the four segments are Search / build skill, Search / save time, Partner / build skill and Partner / save time. Use the existing `segment_forecast_curves.csv` paths: organize figures by acquisition cohort and use the four segments as the series within each figure. Preserve the return metric and its units, the original acquired-customer denominator, the acquisition-cost treatment, the cohort-age axis and forecast uncertainty. This changes the display, not the segmentation or fitted model; save it as a separate view.

The dashboard prompt is the November 12 addition, preserved as FAQ 4 on physical slide 33 of the current 41-slide course deck. Its notes require dated payments and renewals, acquisition-time segment attributes, spending through each cutoff and only experiments whose outcomes were then available. Precompute monthly outputs separately; do not refit on each click. If refits are impractical, show earlier observed results and the original forecast only at the latest month, clearly labeled. This is a proposed follow-up, not an implemented or validated dashboard.

The add-on-revenue prompt was added November 16 as FAQ 7 on physical slide 36. Preserve its per-retained-member denominator, matched customer ages and distinction between sBG retention and the separate revenue model. Its scenarios hold retention and CAC fixed, label future contribution assumptions and save stress tests separately. The prompt does not claim that new revenue models or scenarios have already been run; it changes no released model or guided checkpoint.

When authoring slides, retain all twelve complete prompts in editable text or speaker notes if their on-slide versions need shortening. Preserve the future-model challenge's separate, instructor-held evaluation boundary. Any implemented extension should save its own source, assumptions, inputs, outputs and checks rather than overwrite the frozen reference.

## Companion provenance and reproduction

The archived November 3 companion has 15 native tables, one editable chart and seven complete FAQ prompts in both slide text and notes. Its [provenance record](../teaching/Studio-North-Agentic-AI-Lab-provenance.json) binds the delivered files, source report, input tables and authoring snapshot. The [authoring bundle](../teaching/Studio-North-Companion-Authoring-20261103.zip) preserves the exact scripts, template and frozen content snapshot. It records the authoring-host runtime; it is not a new student setup requirement.

That archived PPTX remains its editable reproduction source. The current main course deck owns the delivered slide order and all twelve FAQ prompts. Microsoft PowerPoint exports its PDF; the analytical report pipeline does not build this deck. Source numbers and all FAQ prompts were checked, all slides rendered in native PowerPoint and inspected, and the final render matched the reviewed pages. The chart's editable workbook stores iCAC rounded to cents; source CSVs retain full precision. These slides reuse the verified Version B outputs and do not claim a new model fit or byte-identical exports across applications.
