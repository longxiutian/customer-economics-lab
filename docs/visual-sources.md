# Visuals, source inspiration and licenses

All numerical figures are original figures made from this lab's saved SQL and
model outputs. The raw records are synthetic. No course slide image, company
logo, student data or article figure is included.

## Archify

The lab invokes Archify's native dataflow, ERD, workflow and architecture renderers.
Inputs are editable JSON generated from raw CSV inspection and declared analytical
relationships. The interactive HTML contains the upstream viewer/template.
One original conceptual business-journey SVG introduces potential benefits and
friction points for Studio North. It is a qualitative orientation, not an observed
customer timeline or a measured satisfaction curve; no segment-specific maps are added.

* Project: [tt-a1i/archify](https://github.com/tt-a1i/archify)
* Version: **3.2.0**
* Pinned commit: `25cf37080fc8b1dbe758a4efc3935b55f3327083`
* Download: [pinned public ZIP](https://codeload.github.com/tt-a1i/archify/zip/25cf37080fc8b1dbe758a4efc3935b55f3327083)
* License: MIT, Copyright 2026 tt-a1i (Archify), Copyright 2025 Cocoon AI.
* Preserved notices: [`vendor/archify/LICENSE`](../vendor/archify/LICENSE),
  [`THIRD_PARTY_NOTICES.md`](../vendor/archify/THIRD_PARTY_NOTICES.md), and the
  bundled font license.
* Archive hash and extraction provenance: [`vendor/archify-provenance.json`](../vendor/archify-provenance.json).

Students use the bundled package and Node.js 18 or later. No Git installation,
GitHub account, remote rendering service or private credential is required.
Renderer validation, browser validation and human visual inspection are distinct
checks. A runtime render log does not imply all three took place.

## Conceptual references

* Juan Orduz, [Revenue Retention and Customer Lifetime Value with NumPyro](https://juanitorduz.github.io/revenue_retention_numpyro/).
  The model is inspired by the separation of retention and spending. It is a
  teaching adaptation with explicit contribution costs and a common horizon;
  the article's text, data and figures are not copied into this repository.
* Gil Bouhnick, [Cohort analysis: how to improve your retention rate](https://www.mobilespoon.net/2019/07/cohort-analysis-retention-rate.html).
  The lab preserves the useful progression from joining cohorts to paying
  customers, revenue and cumulative economics. Its synthetic ledger supplies
  all values. A transaction commission in an example is not automatically a
  complete contribution margin.

The portrait PDF uses an original public LaTeX style in `templates/labreport.sty`.
Source Sans is supplied by the installed TeX font package; the report figures
use the font bundled with Matplotlib. No private template content is copied.

## Figure evidence

`report/chart_manifest.json` identifies each source table and its hash, the
selection or normalization used, and deterministic output hashes. Figures
distinguish customer age from calendar time and observed data from predictions.
Channel acquisition tables retain nonbuyers in the assigned denominator. Reports never
infer campaign causality from differences between acquisition-channel LTVs.
