# Release validation — v2.0.0

The release passed **139 tests**. Two independent processes computed the
statistical pipeline, including three NUTS fits and a Bayesian neural benchmark.
After report-layout repair and added experimental uncertainty columns, the ETL
and report stages were independently replayed for both runs. The three model-input
CSV hashes remained unchanged. **60 canonical artifacts match byte-for-byte**,
including analytical tables, posterior draws, diagrams, figures, TeX and PDF.
See `reproducibility.json` for the precise scope and hashes and `release.json`
for implementation fingerprints. Diagnostic page screenshots are not canonical
scientific outputs.

The tests cover frozen-data regeneration, persistent latent churn heterogeneity,
conditional renewal likelihoods, censoring, acquisition timing, UCV field coverage,
SQL reconciliations, future-data leakage, spending without conversions, unequal
experimental arms and nonbuyers, uncertainty intervals, seeded dispersed NUTS
starts, finite diagnostics, matched holdouts, one-stage-at-a-time behavior,
saved judgments, logged read-only SQL, and ZIP extraction without Git.

The main full-data fit has R-hat **1.0009**, minimum effective sample size
**1412**, and **0 divergences**. The separate historical fits also
pass the documented convergence gate. These are sampling diagnostics, not evidence
that the statistical model is exactly correct.

Twelve-month historical contribution-value MAE is **$3.13 per acquired customer**
across 11 cohorts, versus **$25.21** for the stated baseline.
Only 4 cohorts had payback still in the future at that origin; their zero
month error is a small synthetic-data result, not broad validation. Seven already
recovered cohorts are excluded from that forecast score. Shorter-period held-out
revenue WAPE is **6.11%**, versus **10.81%** for the baseline.

The actual Orduz-derived neural benchmark and the main retention model use the
same **258** held-out observations. Retained-member MAE is **1.112**
for the main model and **1.146** for the neural comparison. The benchmark
does not supply executive LTV. Its architecture and changes from the source are
documented in `docs/orduz-benchmark.md`.

The report has 14 pages, with an A3 schema foldout and otherwise US Letter
pages; all were visually inspected. It has no overfull TeX boxes. The companion
has 12 slides, 5 editable native charts and 5 native tables.
The actual maintained report style is bundled and hash-pinned.

Intervals describe conditional parameter uncertainty, not all future economic
risk. Campaign contribution intervals are approximate 95% sampling intervals
over their actual 31- and 30-day follow-up windows; both include zero.

This evidence covers the documented Windows/CPU environment and WSL pdfLaTeX.
It does not establish bitwise equality on every platform or predictive accuracy
for another business. v1 remains under its immutable tag. Its old sensitivity
receipt is not part of v2 validation. The optional starting-value sensitivity
script has not been claimed as an additional executed release check.
