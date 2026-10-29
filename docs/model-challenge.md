# Optional challenge: improve the future customer-economics forecast

The current baseline uses **hierarchical shifted-Beta-Geometric retention plus Gamma revenue**, estimated in NumPyro on CPU. Investigate another model and explain whether its assumptions and historical validation make it a better forecasting candidate. This is an optional modeling extension; no grading weight or live leaderboard is established here.

## What is being predicted

The observed files end on December 31, 2025. Forecast **January through December 2026 for the same 24 acquisition cohorts**. There are no new 2026 acquisition cohorts in this challenge. Each row is an existing acquisition month × channel × stated need × future calendar month.

Predict expected retained members, net revenue, and contribution in each future month. Fractional expected member counts are appropriate. Contribution deducts refunds and nonmarketing variable costs. Do not subtract CAC again: acquisition costs occurred before this future window.

This is **remaining value over the next twelve calendar months**, not the report's contribution LTV over each cohort's first twelve monthly receipts. An older cohort can have completed its first twelve receipts and still produce valuable revenue in 2026. The oldest cohort requires predictions at ages 24–35, beyond the largest observed age of 23. Explain that extrapolation and the assumptions supporting it.

The [design commitment](../assets/challenge/design-commitment.json) and [sealed-answer commitment](../assets/challenge/answer-commitment.json) record salted hashes established before evaluating model forecasts. They contain no outcomes or random keys. The instructor retains the underlying files and salts for later verification.

## Reproducible baseline and submission

After the SQL stage, create the blank template:

```text
uv run --frozen python lab.py challenge-template
```

After the verified model stage, the baseline predictions are available under `outputs/guided/challenge/`. They can also be generated explicitly without fitting again:

```text
uv run --frozen python lab.py challenge-baseline
```

Keep the same `--output` option used for your analysis. These commands do not advance the guided stage. They preserve existing files rather than overwriting a filled submission.

Copy `submission_template.csv` to a new file such as `my-model-predictions.csv`. Preserve:

| Column | Meaning |
|---|---|
| `cohort_month` | Observed first-paid acquisition month. |
| `channel`, `primary_need` | Observed analytical cell. |
| `calendar_month`, `age_month` | Future calendar month and age since acquisition. |
| `n_acquired` | Original observed acquired-customer denominator. |
| `origin_retained` | Observed members still active at the forecast origin. |
| `predicted_retained` | Expected retained-member count. |
| `predicted_net_revenue` | Expected total net revenue for the cell and month, in dollars. |
| `predicted_contribution` | Expected total contribution for the cell and month, in dollars. |

Fill only the three prediction columns. Membership cannot increase or exceed the origin survivors in this absorbing-churn business. Extinct cells must remain zero. Keep every row, including extinct cells. Contribution cannot exceed net revenue given the recorded nonnegative variable costs.

```text
uv run --frozen python lab.py validate-submission --csv my-model-predictions.csv
```

Validation checks format and business constraints; it cannot tell you how accurate a future prediction is. The future outcomes are held separately by the instructor and are not present in the public repository, its diagrams, report, or skill.

## Evaluation rule

The primary score is **contribution WAPE at acquisition-cohort × future-calendar-month level**. First sum predicted and actual contribution across channel and need within each cohort/month. Then compute:

\[
\mathrm{WAPE}=\frac{\sum_{k,m}|\widehat C_{k,m}-C_{k,m}|}{\sum_{k,m}|C_{k,m}|}.
\]

There are 24 × 12 = **288 cohort/month points**. Lower is better. The denominator is the sum of absolute realized cohort/month contribution and must be positive. Realized refunds can produce negative cash even in a cell with no remaining members; the truth validator permits these outcomes without changing the answer key. This differs from the expected-value constraints on submitted forecasts. Report expected values consistently so fine-cell predictions aggregate coherently. Absolute loss rewards medians for an individual scalar, whereas the required fine-grid estimates must also aggregate across cells; do not treat this score as a complete assessment of uncertainty calibration.

Secondary diagnostics are retained-member WAPE at the submitted cell/month level and signed total contribution bias, `(sum(predicted) − sum(actual)) / sum(abs(actual cohort/month contribution))`. They do not change the primary ranking. The public `cohort_lab.challenge.score_predictions` function implements this exact rule; it receives truth from its caller and never retrieves an answer key itself.

## How to investigate another model

Preserve the released baseline and use a separate experiment folder. State the alternative's retention and revenue assumptions before fitting. Use only the observed data and chronological historical validation to choose specifications; do not use the private 2026 outcomes for tuning. Young cohorts have little renewal history, and a flexible model can extrapolate poorly beyond observed ages.

Use **uv** for every Python dependency and execution step. If a new package is required, use `uv add` in a separate experiment copy and preserve that copy's `uv.lock`. A CPU implementation must remain available; no GPU is required for the supplied baseline or neural comparison. Save the code, exact input hashes, inference seed, fitted parameters, validation design, output predictions and a short model explanation. Generation of the source data is outside the student analysis workflow.

The local [Orduz reading](../assets/articles/orduz-2024-cohort-revenue-retention/orduz-source-notebook.pdf) provides one methodological starting point. Its author's original computational settings are distinct from this repository's CPU implementation. Other defensible approaches are welcome; model complexity alone is not evidence of better customer-economics decisions.
