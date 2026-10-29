# Modeling decisions and verification

## Different generation and inference mechanisms

The v2 sources contain individual monthly renewal decisions for 24 acquisition cohorts. Each acquired member receives one persistent latent churn propensity from a two-component Beta mixture. Group composition and a temporary calendar disturbance vary the observed curves. These simulation variables never appear in the eight analyst-facing CSVs.

Inference uses one Beta distribution per cohort/need/channel cell, covariates and partially pooled cohort effects. This structural difference permits misspecification without injecting arbitrary errors or selecting a seed after inspecting forecasts. Gamma revenue inference also differs from the generator's explicit plan, upgrade and add-on purchases.

The design was deliberated with Claude Opus 5.5 at **xhigh** effort. Codex implemented and executed the tests; the reviewer receives supplied code and test evidence rather than running local tests itself. v1 remains available under its immutable tag. Its earlier linear hazard and SVI checks do not validate the new NUTS model.

## Main model and comparison

Management valuations use hierarchical shifted-Beta-Geometric retention and Gamma gross revenue in NumPyro NUTS. A genuine four-hidden-unit Bayesian neural network separately adapts Orduz's architecture to conditional monthly risk sets. It is a validation comparison, not the source of executive LTV. See [model specification](model-specification.md) and [benchmark provenance](orduz-benchmark.md).

The four-chain convergence gate requires finite diagnostics, R-hat at most 1.01, effective sample size at least 400 and zero divergences. Residual dispersion and held-out errors are reported separately. An independent audit found that NaN diagnostics could bypass ordinary comparisons; explicit finite checks and regression tests close that gap.

## Falsification checks

| Risk | Verification |
|---|---|
| Propensity is redrawn monthly | One latent draw per acquired person, mixture-moment and survivor-selection tests. |
| Censoring becomes artificial churn | Acquisition supplies no renewal trial; future/pending periods are excluded; exactly 24 entry cohorts. |
| Cumulative counts reuse customers incorrectly | Conditional hazard products equal Beta-function survival; individual and aggregate likelihoods agree after count combinatorics. |
| Simulator truth or future outcomes leak | Explicit feature whitelist and held-out outcome mutation tests. |
| CAC drops zero-conversion or unallocated spend | Spending perturbations distinguish whole-company from supported cell CAC; unknown organic CAC stays missing. |
| Forecasts borrow future economics | Training-only backtests and age-aligned contribution-ratio fixtures. |
| Numerical completion is called convergence | Finite diagnostics, R-hat, ESS and divergence gates apply to all three historical/full fits. |
| Short-term retention accuracy substitutes for value accuracy | Three-month outcome holdout plus separate year-end twelve-month contribution-value holdout, both with baselines. |
| Already observed payback is scored as a forecast | Only recovery after the historical origin enters forecast payback scoring. |
| A common seed substitutes for reproducibility | Two fresh processes compare analytical tables, posterior draws, diagrams, figures, TeX and PDF hashes. |
| Old figures or styles are silently reused | Source, model, benchmark, diagram and report manifests bind actual numerical and visual files. |

## Interpretation limits

The decision horizon is twelve monthly receipts. Cash payback is undiscounted; contribution value is discounted at 1% monthly. CAC is deducted once. Parameter bands hold economic ratios fixed and omit renewal/revenue process noise, future costs and regime change. The probability of nonnegative **expected** cash is a posterior-parameter quantity, not a guarantee of actual recovery.

One year-end origin and one three-month holdout do not establish universal forecast accuracy. Cohort and channel differences remain descriptive. Campaign incrementality is evaluated separately using all randomized prospects, including nonbuyers, within its outcome window. Favorable LTV cannot substitute for a controlled test of additional spending.

Executed counts, diagnostics and hash comparisons are recorded under `validation/` and in the report. Receipts identify the tested platform and dependency versions; cross-platform byte identity is not assumed. `scripts/validate_model_stability.py` is an optional starting-value sensitivity check, not an unexecuted release claim.
