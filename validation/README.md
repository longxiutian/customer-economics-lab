# Release validation

The release passed **89 tests**. Two fresh Python processes rebuilt the complete
pipeline; **38 artifacts matched byte-for-byte**, including analytical tables,
posterior draws, diagrams, chart PNGs, editable report source, and the final PDF.
`release.json` binds this evidence to the source files and output artifacts.

The tests cover independent financial fixtures, zero-conversion spending,
unequal experimental arms, all assigned nonbuyers, raw-data as-of replay,
immutable inputs and derived tables, one-stage-at-a-time behavior, saved learner
judgments, logged read-only queries, and ZIP installation without Git.

The 12-month historical valuation backtest covers 11 cohorts: mean absolute
contribution-value error is **$6.72 per acquired customer**, versus **$34.87**
for the naive baseline. Only **four** cohorts had payback still in the future
at that origin; their payback-month error was zero in this synthetic dataset.
Seven already-recovered cohorts are excluded from that score. Shorter-period
held-out revenue WAPE is **5.51%**, versus **11.80%** for the naive baseline.

The report's conditional parameter intervals omit model, optimizer and future
economic uncertainty. See `model-stability.json` and `docs/model-review.md`.
The 1,200-step sensitivity fit is not a release fit; the released workflow uses
3,000 steps and checks diagnostics before reporting.

This evidence covers the documented Windows/CPU environment and WSL pdfLaTeX.
It does not establish bitwise equality on every operating system or predictive
accuracy for a different business. Complete setup and the smoke run on the
classroom platform before teaching.
