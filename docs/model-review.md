# Modeling decisions and verification

## Observed release and independent evaluation

The student workflow starts from eight frozen source exports spanning 24 monthly acquisition cohorts. It contains no generation command, private simulation settings or future evaluation outcomes. A separate instructor workflow creates and checks the observed snapshot and the next twelve calendar months of continuation data. Private generation tests and keys remain outside the public repository.

The main model and its priors are specified independently of the hidden generation process. Cohort improvement must appear in the observed matched-age evidence; the report must not assert a trend merely because the scenario was designed to explore one. Neither the model nor its priors may be tuned on the private future evaluation labels.

Version 4 is deliberated with Claude Opus 5.5 at maximum effort, first on the design and then on the rendered report and companion slides. Codex executes the tests locally; provider consultation is not represented as test execution. The release receipt records the completed reviews and their adjudication. Prior releases remain historical artifacts and do not validate this release's new data or fits.

The design review called for economically meaningful but overlapping customer groups, a distinct cohort trend, and comparisons that separate customer mix from progress within comparable groups. The public report verifies those patterns from the observed records. Its segmentation comparison uses the same mature paid customers and the same six-receipt window for all four two-group strategies, excludes both experimental arms, and retains a cohort-centered diagnostic. Group averages are not treated as causal effects or as evidence that members are homogeneous.

## Main model and comparison

Management valuations use hierarchical shifted-Beta-Geometric retention and Gamma gross revenue in NumPyro NUTS. A genuine four-hidden-unit Bayesian neural network separately adapts Orduz's architecture to conditional monthly risk sets. It is a validation comparison, not the source of executive LTV. See [model specification](model-specification.md) and [benchmark provenance](orduz-benchmark.md).

The four-chain convergence gate requires finite diagnostics, R-hat at most 1.01, effective sample size at least 400 and zero divergences. Residual dispersion and held-out errors are reported separately. An independent audit found that NaN diagnostics could bypass ordinary comparisons; explicit finite checks and regression tests close that gap.

## Falsification checks

| Risk | Verification |
|---|---|
| Source generation enters the student analysis | Public export/schema/hash tests and a separate instructor-only generation workflow. |
| Censoring becomes artificial churn | Acquisition supplies no renewal trial; future/pending periods are excluded; exactly 24 entry cohorts. |
| Cumulative counts reuse customers incorrectly | Conditional hazard products equal Beta-function survival; individual and aggregate likelihoods agree after count combinatorics. |
| Future outcomes leak | Declared feature whitelist, chronology/mutation tests and an observed-only submission grid; evaluation labels are not shipped. |
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
