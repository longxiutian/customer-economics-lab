# Optional challenge: improve the future customer-economics forecast

The current baseline uses **hierarchical shifted-Beta-Geometric retention plus Gamma revenue**, estimated in NumPyro on CPU. Investigate another model and explain whether its assumptions and historical validation make it a better forecasting candidate. The team with the best private-holdout performance earns **one bonus point**. The instructor handles ties and submission timing; no live leaderboard is promised.

## What is being predicted

The observed files end on December 31, 2025. Forecast **January through December 2026 for the same 24 acquisition cohorts**. There are no new 2026 acquisition cohorts in this challenge. Each row is an existing acquisition month × channel × stated need × future calendar month.

December 2026 is a common **calendar endpoint**, not a common customer age. Every cohort has twelve future months because every cohort's observed history ends in December 2025. Younger cohorts have a greater forecast share of their trajectory's months, rather than more forecast months:

| Acquisition cohort | Observed months through December 2025 | Months to forecast | Forecast cohort ages |
|---|---:|---:|---|
| January 2024 | 24 | 12 | 24–35 |
| January 2025 | 12 | 12 | 12–23 |
| December 2025 | 1 | 12 | 1–12 |

Age zero is the acquisition month. The observed cohort-age view is triangular; extending every cohort to the same calendar endpoint adds twelve future observations per segment to each cohort's trajectory, at different ages. A common cohort-age endpoint would instead give younger cohorts more remaining months, but that is a different evaluation target. Forecast share of months is not the same as forecast share of dollar value.

Predict expected retained members, net revenue, and contribution in each future month. Fractional expected member counts are appropriate. Contribution deducts refunds and nonmarketing variable costs. Do not subtract CAC again: acquisition costs occurred before this future window.

This is **remaining value over the next twelve calendar months**, not the report's contribution LTV over each cohort's first twelve monthly receipts. An older cohort can have completed its first twelve receipts and still produce valuable revenue in 2026. The oldest cohort requires predictions at ages 24–35, beyond the largest observed age of 23. Explain that extrapolation and the assumptions supporting it.

The archived [design commitment](../assets/challenge/design-commitment.json) and [sealed-answer commitment](../assets/challenge/answer-commitment.json) remain unchanged for provenance. They predate dataset 5.0 and do not certify an answer file for its revised customer population. They contain no outcomes or random keys.

The instructor has now reconciled and sealed an answer file for exactly the **5,703 released customers**: 96 acquisition/channel/need cells and **1,152 future rows**. The already realized person-level records were restricted to these customers before canonical SQL aggregation. All six customer-history tables and every historical aggregate match the sealed observed records. No future outcomes were redrawn and no forecasts were read or scored during reconciliation. The [current public commitment](../challenge/answer-commitment.json) binds this derived edition; the answer file, salt and source records remain private.

## Team repository and prediction interface

After completing the guided lab, ask your agent to use [the challenge skill](../skills/model-challenge/SKILL.md). It can create a separate team project with:

```text
uv run --frozen python scripts/create_challenge_repository.py --destination ../studio-north-team-model
```

The project contains a runnable example, `pyproject.toml`, `uv.lock`, a public prediction grid, and the [machine-readable contract](../challenge/submission-contract.json). The constant-hazard example demonstrates the interface; it is separate from the official hierarchical sBG + Gamma reference.

Expose this function in `main.py`:

```python
def predict(tables: dict[str, pandas.DataFrame],
            prediction_grid: pandas.DataFrame, *, seed: int) -> pandas.DataFrame:
    ...
```

`tables` has eight keys matching the released CSV filenames without `.csv`. Columns match the released schemas; dates are ISO strings, numbers are numeric, and nullable blanks are missing. The function receives only history available through December 31, 2025, plus the grid's future keys and observed exposures. The private future CSVs are evaluation targets and are never passed to submitted code.

In the separate team folder, the standard execution is:

```text
uv sync --frozen
uv run --frozen python main.py --data-dir /path/to/released/data --prediction-grid prediction_grid.csv --output outputs/predictions.csv --seed 20261116
```

The common budget is **60 minutes, four CPU cores and 16 GiB memory**, using Python 3.12 with no GPU or runtime network. Dependency preparation is separate; fitting and prediction both count toward the budget. Fit from the supplied data rather than requiring precomputed fitted files. Save deterministic predictions with the declared seed. Submit a **public GitHub repository URL and full commit SHA**, including the entry point, locked dependencies, contract, model explanation and chronological validation. The instructor records runtime and hashes, validates the output, then scores it in a separate process. Invalid or incomplete submissions receive a failure reason rather than a partial-grid accuracy score.

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
