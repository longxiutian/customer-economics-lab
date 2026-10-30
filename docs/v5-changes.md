# Release 1.5: journey diagnostics and model-based cohort forecasting

The historical labels in this note use the original numbering. See [the release mapping](versioning.md) for the 2026 1.x series and preserved original tags.

Version 5 preserves the version 4.0 source exports, baseline model code, posterior draws and neural comparison. It changes the management report and adds auditable diagnostic and post-estimation outputs. The v4.0.0 release remains available.

The report opens with the requested Studio North title and a table of contents. The former forecast-horizon section now follows Company economics as **Model-based forecasting of cohort trajectories**. It explains persistent churn heterogeneity, the renewal likelihood, revenue, censoring and the forecast horizon before displaying predictions. The requested disclaimer sentence is removed. Parameter estimates and validation remain in the technical appendix.

## Journey evidence

`sql/02_friction.sql` creates diagnostic populations from events, onboarding feedback and renewal records. Features use the half-open 27-day interval after first payment. Both randomized arms are excluded; customers are never selected for surviving. Survey categories remain nominal, with no recorded response and unanswered items separate from “none.” Invitations and cancellation-request times are unobserved.

First-renewal retention is primary. Age-5 retention and ages 1–5 contribution provide economic follow-through with original-customer denominators and zeros after exit. Future outcomes remain missing. Timing audits check exposure, renewals, effective cancellations, refunds and transaction overlap. Refunds remain in the main denominator; a separate sensitivity excludes members with an in-window refund.

`cohort_lab/diagnostics.py` exports descriptive contrasts. Event contrasts align acquisition year, channel and need. Survey contrasts align acquisition month, channel and need, require common support and report coverage. Approximate normal intervals use fixed empirical weights and independent-person sample variances. These are neither causal effects nor equivalence tests. The report returns to the conceptual journey, shows all 24 cohorts within need and documents measurement gaps and group composition.

## Strategic acquisition segments

`cohort_lab/postestimation.py` reads the frozen posterior and the baseline model's path functions. It reconciles all 98 acquisition-cell valuations and all 24 whole-cohort trajectories before selecting an exhibit. No parameter is re-estimated.

The breakout selects July 2025 by maturity and assignment: the latest four-cell paid cohort with six observed receipts and no experimental buyers. July 2024 supplies a same-season contextual comparison. Tables show tracked CAC, discounted contribution before and after CAC, forecast share, observed retention and observed cash payback. Trajectories separate observation from forecast. A cross-cohort check reports the within-channel need ranking, excluding pairs containing experimental buyers and separately counting fully observed pairs.

The bands describe uncertainty in the unobserved expected remainder, with realized receipts and CAC fixed. Average value does not identify marginal budget returns. No CAC or model value is assigned to activity or survey groups. The main valuation remains sBG plus Gamma; the Orduz-inspired neural model remains a separate validation comparison.

## Reproduction and teaching

The companion retains twelve slides and all numerical exhibits. Handoff guidance and notes now match the report order, journey diagnostics and strategic breakout. Native charts and their original embedded workbooks are preserved.

For a report replay without refitting, use a fresh output folder:

```text
uv run --frozen python scripts/replay_report.py --source examples/reference --output outputs/report-replay --instructor
```

This independently rebuilds observed SQL, diagnostics, post-estimation paths, diagrams and the PDF, validating reused fitted inputs. It is distinct from the full inference reproducibility command in the README. Exact release checks and scope are recorded in `validation/`. The guided student workflow still advances only after an explicit “next.”

The cover identifies Kenan-Flagler Business School, MBA 743: Managing Customer Data, Mod II 2026. The opening section is "Studio North and the customer journey." Author-year citations link adapted methods to a references page, including the licensed Orduz notebook in `assets/` and its exact role in the revenue model and separate neural comparison.
