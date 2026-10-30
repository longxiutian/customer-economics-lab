# Reproduce the lab and preserve its decisions

Run every command below from the extracted repository with the frozen environment in [setup](setup.md). No Git, private skill, private helper, course PDF, data generator or future outcome is needed. Keep new output directories separate from `examples/reference` and learner work.

## Three different verification claims

**Validate saved artifacts without recomputation:**

```text
uv run --frozen python scripts/validate_artifacts.py --output examples/reference --companion
```

This validates frozen raw inputs, SQL-derived outputs, both fitted models and their matched validation cells, journey diagnostics, segmentation/CAC metrics, posterior post-estimation, diagrams, figures, editable report source, styles, PDF and source bindings. The implementation manifest includes Python and Node scripts, both skills and their references, linked documentation, vendored Archify files and dependency locks. The companion flag additionally checks its frozen PPTX/PDF and the six analytical source-table hashes. Integrity does not establish numerical correctness or visual quality on its own.

**Rebuild the report twice without fitting either model:**

```text
uv run --frozen python scripts/verify_reproducibility.py --mode report --source examples/reference --output outputs/report-repro
```

Each fresh Python process validates and copies only the baseline and neural manifests and their declared fitted outputs. It rebuilds observed DuckDB ETL, diagnostics, decision metrics, posterior post-estimation, diagrams, figures, editable TeX and PDF. It verifies the resulting evidence chain, then compares every canonical artifact. The original eight CSVs, synthetic holdouts, posterior draws and fitted outputs are preserved. `report_replay.json` records the reused hashes; `reproducibility.json` explicitly records `model_refit: false`. This mode does not recreate the optional twelve-calendar-month challenge predictions or learner choices. It builds the analyst reference report.

For a single report replay, use:

```text
uv run --frozen python scripts/replay_report.py --source examples/reference --output outputs/report-replay --instructor
```

**Refit and rebuild everything twice:**

```text
uv run --frozen python scripts/verify_reproducibility.py --mode full --output outputs/full-repro
```

This is the expensive instructor check: each process runs both models, the observed analysis, validation, challenge predictions and the report. The main model uses CPU float64, seed 20261116, four sequential NUTS chains and the released budget; the separate neural benchmark has its own saved settings. See [model specification](model-specification.md) and [Orduz benchmark](orduz-benchmark.md). `--mode full` remains the default for backward compatibility. `--steps` is accepted only for this mode and must be at least 3000. `--parallel` runs the two isolated processes concurrently if memory permits. Neither command is a replacement for the student's explicit `next` gates.

Add `--no-pdf` to either verifier or the single replay only when editable TeX is sufficient. The receipt then excludes the final report PDF. Figure PDFs and diagrams still require their ordinary dependencies. Use `validate_artifacts.py --no-pdf` for that result; never describe it as a compiled report.

## What is compared and preserved

The verifier includes all numerical tables, saved SQL, analysis/input/model/benchmark/diagnostics/decision-metrics/post-estimation/implementation manifests, summaries and posterior draws; diagram JSON, HTML, SVG, PNG, UCV Markdown and inspection SQL; report TeX, style files, manifests, registry, evidence tables, figures and optional PDF; and challenge or replay receipts where that mode produces them. It validates the manifests before comparison, so two identically stale outputs do not pass. Logs, learner state, ad hoc query receipts, previews and page renders are separate evidence, not canonical output comparisons.

`implementation_manifest.json` is bound into the report manifest. It also drives guided-session invalidation. Changing instructions, executable source, a lock or a vendored dependency requires a fresh output folder or restoration of the prior release. Do not edit a hash receipt to make an old result pass. Saved SQL questions remain under the learner's output directory and do not change the canonical implementation.

Byte equality is a same-host, same-environment claim. Pin Python and Node dependencies, retain the compiler engine recorded in the report manifest, use Source Sans and the fixed source-date epoch **1794787200**, and preserve the browser's fixed viewport, locale, timezone and animation settings. Record the actual host and tools. Different operating systems, TeX/font installations, BLAS/JAX builds or browsers can change bytes; independently check numerical and visual agreement before claiming support for another platform.

## Durable requirements from the report revisions

| Requirement | Authoritative instructions and implementation | Saved evidence |
|---|---|---|
| Centered two-line title, centered evidence/cutoff, left-aligned three-line school/course/term credit; customer **journey** heading; model immediately after company economics; separators and technical appendix | [Executive report skill](../skills/executive-report/SKILL.md), `templates/customer-economics-report.tex.j2`, `templates/labreport.sty` | Editable TeX, PDF metadata, exhibit registry, report/style manifests and visual review |
| Explicit citations and reference list, including the Orduz adaptation, Larsen and MBA 743 Topic 1/3/4 connections | [Sources](sources.md), [CAC methodology](cac-incrementality.md), `assets/articles/` provenance and licenses | Citation/reference anchors in TeX and PDF; licensed Orduz notebook/PDF hashes. A citation alone grants no redistribution right. |
| Within-cell homogeneity and across-cell heterogeneity on equal customers, horizon and cell count; residual dispersion and actionability | Root skill stages 2/4, [CAC methodology](cac-incrementality.md), `decision_metrics.py` | `segmentation_comparison.csv`, `segmentation_profile.csv`, `segmentation_objective.csv`, `decision_metrics_manifest.json` |
| Early journey signals with [0,27)-day exposure, both experimental arms excluded, original denominators, survey missingness, common support and uncertainty | Report skill, `sql/02_friction.sql`, `diagnostics.py` | `friction_*` SQL tables, contrasts, balance, refund sensitivity, `diagnostics_manifest.json` |
| Acquisition-stratum LTV and observed/forecast payback; maturity-based example selection and cross-cohort ranking checks | Report skill, `postestimation.py`, unchanged model path functions | Reconciliation of all baseline cells/paths, strategic breakout, segment curves, ranking stability, `postestimation_manifest.json` |
| Attribution-style media-per-buyer benchmark → scaled-control background → incremental buyers → iCAC with uncertain denominator | Root skill stage 5, [CAC methodology](cac-incrementality.md), `decision_metrics.py`, `decision_report.py` | Original all-assigned experiment summaries/effects, `cac_reconciliation.csv`, manifest and dedicated CAC chapter |
| Observed blended CAC paired with average cohort contribution LTV; campaign decisions use matched incremental all-assigned value and costs | Same methodology note; report and root skills | Matched cohort accounting; explicitly scoped 30/31-day test-program calculations. No relabeling as company-wide incremental or marginal CAC, no double subtraction, no unidentified lifetime uplift. |
| All 24 cohorts, comparable ages/weights, missing future cells, stable dark retention labels and signed cash colors | Root and report skills, `report.py`, `display.py`, saved SQL | Chart manifest, matched-cohort evidence, executive metrics, complete figures and original-denominator tables |

The revised skills preserve decisions, not frozen numerical answers: derive displayed values from validated saved outputs. Retain the existing synthetic experiments; no data regeneration or model refit is needed to explain incrementality. Distinguish lab undiscounted cash payback from the course's discounted contribution payback.

## Visual and companion checks

The report compiler checks designed pagination, page dimensions, literal code/field copyability and overflow. Visual review is still required: render **every** page, inspect a contact sheet, and inspect every changed page at full resolution. Use a local PDF renderer such as Poppler (a separate optional QA tool), for example:

```text
pdftoppm -r 110 -png outputs/report-repro/run-a/report/customer-economics-report.pdf outputs/report-repro/page
```

Check cover line placement and metadata, contents/order, citations, blank pages, clipping, type hierarchy and figure/table readability. Preserve Letter portrait pages and the single A3 landscape schema foldout. Do not shrink the body globally to hide overflow. Save the inspection scope and results separately from computational receipts. See [format provenance](report-format-provenance.md) for the unmodified vendored style.

`teaching/customer-economics-lab.pptx` is the editable companion source, including native charts, embedded chart workbooks, tables and notes; its paired PDF is a frozen native PowerPoint export. `teaching/companion-provenance.json` binds both and their analytical sources. The report pipeline does **not** author or render this separately maintained deck, and its slides do not automatically acquire new report sections. Preserve it when its content is unchanged. If revising it, update native data from verified tables, use the shared retention formatter, retain chart editability, export through a recorded presentation renderer, and inspect every slide. Record the revised source-table and file hashes and actual rendering scope; do not claim a new deck build from a report replay. A fresh PowerPoint export can have different metadata bytes while preserving visual content.

## Portable release handoff

Before release, run the affected behavioral tests (`uv run --frozen python -m pytest ...`) and the applicable verification mode. Re-run broader model tests or fresh inference when model/source/settings changes warrant them; a skill or layout correction alone does not call for new simulation data. Verify frozen assets and record which tests actually ran.

Distribute the final source, locks, both skills and linked notes, assets/licenses, editable report/PPTX sources, canonical reference artifacts and scoped validation receipts together. Preserve prior release tags. After publication, download that exact tagged ZIP over HTTPS, extract it into a new folder without `.git`, and run `uv sync --frozen` (select an existing Python 3.12 with `--python` if needed), then the saved-artifact validation command above. Install the locked Node/browser and TeX dependencies when exercising a new replay there. Compare the downloaded report/companion/reading to their recorded hashes. Record source-ZIP verification separately from computation and visual review. The publisher's private boundary audit is an additional release check; public users never need its private inputs.
