# Version B comparison

Version B is an editorial comparison against the frozen 1.7.0 report, called Version A. It does not replace that release or change the 2026 semantic version. A remains at `examples/reference/report/customer-economics-report.pdf` with SHA-256 `af7736315146fa3951007291c98d5d8054f2c3f362fdf7579089379d3e0dbd8b`. Verify the exact hash in the comparison receipt; do not regenerate A to create the comparison.

## The executive contract

Count **15 physical pages before the appendix, including cover and contents**. The appendix begins on physical page 16. Preserve the exact title, course credit, dates, citations and source assets. Retain the base typography. Remove the nine main-section separator pages and use descriptive headings plus the contents instead.

The narrative is: conclusion and acquisition recommendation; business and journey; descriptive acquisition holdouts; observed retention and cash; segmentation and within-group improvement; company economics; plain-language model explanation; first-year value; historical CAC versus pilot iCAC and cash recovery; acquisition choice; management action. The model explanation follows company economics and precedes every forecast exhibit.

Write for the manager of a capable MBA, roughly ten years beyond their own MBA. Make a concrete recommendation, name its economic basis, and state decision-changing uncertainty where it affects that recommendation. Move derivations, detailed diagnostics, source filenames, data dictionaries and reproducibility mechanics to the appendix. Do not turn every finding into a generic limitation. Keep material assumptions: the additional buyers' transferred value path, the forecast share, cost uncertainty, and a funding decision that Finance has not yet made.

The segmentation objective remains **within-cell homogeneity and across-cell heterogeneity** on a common population, outcome horizon and cell complexity. Show both its useful group-level difference and the residual individual variation. Preserve the operational journey diagnostics in Appendix C.

## Same evidence, explicit presentation calculations

Use the frozen eight datasets and fitted main/neural outputs from A. Experiments remain limited to acquisition; no experimental revenue, renewal or journey outcome enters the model. Rebuild observed SQL, diagnostics, post-estimation and presentation artifacts from their saved inputs.

`cohort_lab/report_b.py` restores historical CAC to the saved cumulative cash path, then finds its first crossing of pilot iCAC. Payment one is the joining month. This is conditional expected cash recovery, not an observed experimental payback. Discounted first-year contribution value before CAC minus iCAC is the corresponding planning surplus; do not subtract historical CAC again. Keep the cost interval separate from model uncertainty. Break-even value share is iCAC divided by the matched first-year contribution value.

The selected candidate is the tested campaign with the largest point value less iCAC. The case narrative is guarded against changed findings; new data require a review of the recommendation, not merely refreshed numbers.

The B templates are `templates/customer-economics-report-b.tex.j2` and `templates/customer-economics-appendix-b.tex.j2`; `templates/labreport-b.sty` supplies the variant's cover, header and contents adjustments without changing A's style. The main-body source map and calculation evidence are saved under `report/`. Complete prior-only coefficient rows remain in the parameter CSV, while the appendix display omits the unsupported organic-channel coefficients in this two-channel reference case.

## Reproduce

From the repository root, install the locked environment:

~~~text
uv sync --frozen
~~~

Use a fresh output directory for a single B replay:

~~~text
uv run --frozen python scripts/replay_report.py --source examples/reference --output outputs/version-b --variant B --instructor
~~~

For two independent report rebuilds, integrity checks and byte comparison:

~~~text
uv run --frozen python scripts/verify_reproducibility.py --mode report --source examples/reference --output outputs/version-b-repro --variant B
~~~

Both commands reuse verified fitted outputs; neither is a model refit. The default variant remains A. B is supported by report replay, not the full-refit verifier. The standard dependencies and Windows/WSL TeX workflow are documented in the main reproducibility guide; no private helper script is required.

## Acceptance

- A's PDF remains byte-identical; it is a frozen historical artifact, not a claim that its old implementation manifest matches the revised source.
- B has 15 pre-appendix pages, a correctly sized schema foldout, resolved citations/references, and no overfull content.
- Figures, tables and narrative quantities trace to saved results; iCAC recovery and first-year surplus use the correct cost and value bases.
- Literal dataset/field names remain copyable in the appendix. Every B page is visually inspected.
- The report manifest records variant B and binds the B templates, additional artifacts and implementation snapshot. Independent replay equality is reported separately from visual review.
