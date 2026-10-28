# Model decisions and adversarial checks

The implemented model was reviewed with Claude Opus 5.5 at **xhigh** effort. The
model reviewed supplied code and executed-test receipts; it did not run the local
tests itself. Codex implemented and executed the resulting checks. An earlier
proposal-review call failed upstream without a substantive answer and is not
counted as a completed review.

The review led to these changes:

| Risk | Implemented treatment | Falsification check |
|---|---|---|
| Company CAC omits spending in cells with no buyers | Whole-cohort costs come from the SQL spending ledger, separately from buyer-linked segment CAC. | Add zero-conversion and unallocated spending; company CAC must rise while supported segment CAC stays unchanged. Missing paid-cell cost records fail. |
| Young-cohort margins inherit acquisition-month costs | Forecast economic ratios match channel, need, and customer age, with observed renewal ages as a documented fallback. | A fixture with 10% acquisition-month margin and 50% later margin must use 50% for renewals. |
| Historical summaries use future information | Raw exports are physically truncated to an earlier observation date and the SQL is replayed. | All previously observed customer/cohort/company tables and completed experiment outcomes must remain identical. |
| Short-term revenue accuracy is mistaken for LTV accuracy | Add a historical year-end origin and forecast each eligible cohort to a common 12-month horizon. | Compare contribution LTV and cash-payback month with subsequently observed outcomes, using training-only economics. |
| Numerical completion is called convergence | Release fitting uses 3,000 steps, CPU float64 checks, loss-drift and residual-dispersion gates. | Perturb initialization tenfold; inspect value means, interval widths, and likelihood residuals. The release threshold is a diagnostic, not a proof of convergence. |
| Payback hides a later refund reversal | Retain the standard first-crossing definition and add an explicit recrossing flag and probability of nonnegative cash balance at the horizon. | A cash-flow fixture crosses acquisition cost and later falls below it. The flag must distinguish those outcomes. |
| A zero-based age is mistaken for a one-based payback period | Store `payback_age` from zero and `payback_month` as the number of monthly receipts from one. | Boundary fixtures distinguish observed from forecast crossings; valuation and backtest files use the same receipt convention. |
| Already-observed payback is counted as a successful forecast | Score payback only when it occurs after the historical forecast origin. | Four release cohorts have genuinely future payback; seven already-recovered cohorts are excluded from that score. |
| Conditional intervals are overstated | Label intervals as approximate posterior **parameter** uncertainty under the model and fixed future economic ratios. | No claim of full predictive coverage, uncertain future cost ratios, or causally identified lifetime marketing value. |

The model intentionally reports **12-month contribution value**, not an
infinite-lifetime estimate. A positive predicted net LTV does not establish that
additional campaign spending causes that value. The randomized campaign analysis
keeps its own eligible population, control group, and shorter outcome window.

The reviewer accepted the revised approach subject to closing the payback-unit
and scoring issues and rerunning final-release tests. Those issues are covered
by the tests above. Conditional parameter intervals omit optimization sensitivity
and uncertainty about future economics. Different initialization scales shifted
the latest cohort's mean value by about $3; historical 12-month value error
averaged about $7. The shared cohort trend may smooth recent deterioration, so
an observed versus one-step-fitted plot covers the latest six cohorts. This is
an in-sample diagnostic, not a substitute for the held-out tests.

Company CAC uses all acquired customers and tracked spending. May 2025 and
September 2025 include 24 and 26 organic control buyers, respectively. That
changes the blended denominator; it does not establish free organic acquisition
or improvement in paid-channel efficiency.

`scripts/validate_model_stability.py` reproduces the initialization check.
`scripts/verify_reproducibility.py` runs the full pipeline twice in fresh Python
processes and compares scientific outputs and presentation artifacts. The release
validation receipt states which platform and dependency lock were actually tested;
it does not promise bitwise identity across untested machines.
