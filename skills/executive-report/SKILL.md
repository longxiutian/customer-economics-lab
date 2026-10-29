---
name: customer-economics-executive-report
description: Produce and verify the lab's decision-facing executive report with its bundled Source Sans, forest-green and ochre LaTeX system, derived numerical claims, model explanation and technical appendices.
---

# Executive customer-economics report

Use this supporting skill at the reporting stage of the repository's main `SKILL.md`. It is self-contained: the student does not need the author's private skills, private source documents, a Git installation, or an external report template. Resolve all paths from the repository root.

## Read and preserve the visual system

- Read `skills/executive-report/references/style-system.md`.
- `templates/longxiu-research-brief.sty` is the vendored visual source of truth. Preserve it unchanged unless the user explicitly requests a style-system revision.
- `templates/labreport.sty` supplies report-specific semantic wrappers. Typography, colors, geometry and callouts belong here, not in content-generating Python or repeated TeX literals.
- `templates/customer-economics-report.tex.j2` supplies report structure. It is not a classroom worksheet.
- `templates/report-style-manifest.json` pins the vendored package and records its public provenance. `docs/report-format-provenance.md` explains the adaptation.

## Write for an executive who will hand the work to a team

Begin with a concise business description: what is sold, who buys it, how renewal and revenue occur, the decision horizon and what management needs to decide. Give the recommendation and the two or three facts that justify it on the first page. State the evidence period separately from the report build date.

The organizing question is whether successive acquisition cohorts are producing a more durable and economically attractive business. Connect retention, contribution, acquisition efficiency and cash recovery. Acquisition-channel decisions are subordinate to this company-level question.

The opening indicators must measure acquisition efficiency, customer value and cash recovery at matched cohort ages. A latest-month customer count or revenue total can provide scale context, but cannot substitute for the economic diagnosis. Bind the displayed indicators to a saved evidence CSV. Label company-wide tracked-spend/all-acquired-customer cost as **blended CAC**, including the treatment of organic buyers; do not silently call it paid-channel or incremental CAC.

Compare the same acquisition months across years, rather than selecting the earliest and latest favorable endpoints or unmatched seasonal windows. Here the primary comparison is January–June 2024 versus January–June 2025 at age 5, meaning six observed monthly receipts. Weight cohort-level per-customer economics by original acquired counts so that contribution less CAC still equals cash. To assess composition, show paid retention both raw and standardized to the earlier channel-by-need mix. Save exact windows, weights, source hashes and results; this descriptive standardization does not identify a causal effect or eliminate every customer difference.

Check whether experimental buyers change the accounting comparison. Keep the reported whole-company measures and the original windows, mark test months, and disclose a saved-SQL sensitivity excluding both assigned test arms, all their later contribution, and spending inside the test design. Do not exclude only treatment buyers, leave their later receipts behind, remove ordinary campaign spending or call the sensitivity a causal adjustment. Finance's monitoring benchmark should use the comparable ex-test figure when ordinary future cohorts will not contain those tests.

Write complete conclusions, not instructions to a learner. Do not put prompts such as "choose a next action," blank judgment fields, course-stage descriptions, "in this exercise," or an instructor reference-build placeholder in the PDF. The chat skill owns guided questions and stage gates. The report owns the management diagnosis and a concrete action plan. A saved student's judgment may appear as a management recommendation, with its evidence and limitations intact.

## Establish the model before presenting its results

Explain the business mechanism and observed data the model represents before displaying forecast curves or LTV results. Name the likelihood, parameter meanings, sources of heterogeneity, right-censoring treatment, estimation method, extrapolation horizon and economic conversion. Distinguish customer retention from revenue per retained customer and contribution from revenue. Do not imply that the model is the source article's exact implementation when it is an adaptation.

Use observed data at comparable ages to establish the diagnosis. Label forecasts and intervals. State what uncertainty the intervals include and omit. Keep a fitted-value diagnostic distinct from a genuinely held-out prediction check. A predictive LTV model does not identify causal acquisition effects.

## Number and preserve the complete exhibit sequence

Give every report figure and table a consecutive number, a descriptive caption, and a stable cross-reference label. This includes architecture and knowledge-asset diagrams, customer journey maps, parameter and validation tables, and every dataset-specific UCV table. Refer to exhibits by number in the prose. Bind the numbered exhibit registry to the report manifest and fail on duplicate labels or unresolved references.

Show all 24 acquisition cohorts in the observed retention and cash triangles, with all observed ages 0–23. Leave future cells blank; never replace them with zero or truncate the report to a few favorable cohorts. Split dense triangles onto separate pages instead of shrinking labels. For many cohort curves, use aligned small multiples, common tenure/retention axes, a continuous chronological color key, and lines ending at observed ages. An acquisition cohort with no observed renewal can only contribute its age-zero point. Do not smooth away actual variability or create a 24-item legend that consumes the figure.

Retain the need-specific customer journey maps in the management report and connect them explicitly to the raw-data UCV classification. Label journeys as hypotheses and distinguish them from observed event timelines. Keep the eight field-level UCV tables discoverable through numbered references from the main report, rather than leaving their existence implicit in an appendix.

## Required appendices

Every modeling report must include a technical appendix, even when the main document is brief. Include:

1. Model equations, likelihood, priors, parameter estimates and meaningful units; explain transformed parameters and reference groups.
2. Estimation settings, diagnostics, held-out evaluation design and results, and the uncertainty/identification boundary.
3. Data scope and quality checks, observation cutoff, cohort definition, retained-customer denominator, cost scope, and missingness rules.
4. One table **per raw dataset** organized by all four Universal Customer View categories: Identifiers, Engagement, Relationship and Perception. Name concrete fields and explain what they do or do not measure. An empty category should say it is not observed; do not invent a measurement to fill the table.
5. Exact source and build provenance. The illustrative data-generation process may be documented separately from the fitted inference model; never describe a deliberate model mismatch as an exact recovery test.

For historical valuation checks, show the cohort rows in observed-history order, including how many months were observed and forecast. Separate already-observed payback from genuinely forecast recovery; report the latter's sample size rather than treating a small zero-error result as broad validation. Explain when total-value error equals forecast-tail error because the observed prefix is identical. State any baseline fallback used when no renewal history exists. Expected-path payback is not a distribution of realized payback times.

Give exact feature transformations and reference groups from the implementation. Do not describe two differently scaled cohort-trend variables with the same unit. Distinguish retained-count error from revenue error when comparing models. If both simulator and inference model contain customer heterogeneity, say so; describe the actual missing mechanisms rather than implying that the fitted model assumes identical customers.

Use the bundled Archify-rendered data architecture to show table grain, join keys, cardinality and analytical outputs. Preserve the distinction between an observed customer-event timeline and a conceptual journey. Do not substitute a decorative database icon or a single generic UCV table for the dataset-level documentation.

## Numerical and reproducibility contract

All report quantities come from saved, hash-verified SQL/model outputs. Display selection, formatting and explicit weighted presentation summaries may occur in `cohort_lab/report.py`; do not silently recompute a competing aggregate from raw data. Preserve the windows and weights of those summaries in audit outputs. Derive narrative direction, dates, comparisons and recommendations from the same saved evidence used by figures. No hardcoded empirical result or arbitrary current date.

Use `uv sync --frozen` and `uv run --frozen` for Python setup and execution. The student analysis is CPU-capable and starts from the released records. Data generation and the next-twelve-month competition holdout are maintained privately in a separate instructor skill; neither belongs in the analysis skill, report assets or public repository. The report may state that the records are original and synthetic, but must not reveal private simulation parameters or future outcomes.

Preserve the full compiler input, bundled style package, rendered figures, parameter table and manifests. Fix metadata dates through the documented build epoch. Compare complete report output from independent builds, not only an in-memory rerun. Record hashes of both the upstream package and the report wrapper. A changed input invalidates its downstream result.

## Build and visual verification

Use the repository's report command and supported native TeX engine. Source Sans is required; do not silently substitute another report typeface. Compile with shell escape disabled. Preserve editable sources if compilation is unavailable.

Render every PDF page. Inspect a contact sheet and every changed page at full resolution. Verify US Letter portrait dimensions for the main report and appendices, except the explicitly labeled A3 landscape schema foldout. Check selectable text, correct page count, no accidental blank pages, no clipping, no overfull boxes, and a readable hierarchy. Keep the maintained body size; repair overflow through content organization and space allocation rather than globally shrinking text.

Check that all claims in the executive summary are supported later, model explanation precedes model results, every dataset has all four UCV categories, appendices contain actual parameter output, and the report can be reproduced after downloading and extracting the public repository without a private skill installation.

Check literal commands and field names in the actual PDF text layer. Require exact extraction of `uv sync --frozen`, `uv run --frozen`, every source filename and every schema field. A visually plausible dash or spaced monospace token is not sufficient. Use the wrapper's literal `Code` macro with monospace ligatures and expansion disabled, and keep contextual daggers outside field tokens. Give dense journey maps and residual diagnostics sufficient page space; do not hide tiny labels inside large white figure margins.
