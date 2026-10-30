# Version 6: segmentation objectives and incremental acquisition cost

Version 6 strengthens the management report's segmentation objective and adds a dedicated **Acquisition cost and incrementality** chapter, retaining the existing experiment and management-action exhibit. It follows the MBA 743 course connections documented in [the methodology note](cac-incrementality.md).

The report explicitly compares within-cell homogeneity with across-cell heterogeneity on the same customers, outcome horizon and cell count. A weighted variance decomposition makes the improvement and remaining dispersion visible. Journey diagnoses and acquisition strategy cells retain their distinct uses.

The CAC chapter reconciles an attribution-style treatment-arm benchmark with holdout-based incremental buyers and media cost. It includes unequal-arm formulas, interval inversion, a narrowly scoped tested-program sum, and the distinction between matching cohort accounting and matching causal intervention value. The original cohort blended CAC remains correctly labeled as observed accounting cost. It is not relabeled as a causal estimate. The cash-payback convention is distinguished from the course's discounted-payback convention.

## Implementation and provenance

`cohort_lab/decision_metrics.py` reads four existing SQL output tables and produces `segmentation_objective.csv` and `cac_reconciliation.csv`. It reconciles the variance decomposition to the saved profiles and the experiment effects to the existing intention-to-treat outputs. It does not create a competing raw-data aggregation path. `decision_metrics_manifest.json` binds exact code, input and output hashes and records scope, uncertainty and pooling assumptions. Report and chart manifests bind it; the logged query helper validates it before exposing its tables; guided invalidation archives it with dependent outputs.

Independent counterexamples check the course partition arithmetic, customer weights, unequal assignment sizes, nonzero control costs, weak lift, separately standardized pooling and inconsistent saved effects. The guided student stage gates are retained.

The eight source CSVs, original SQL aggregation, all 37 previously released numeric tables, baseline model code, posterior draws and neural benchmark artifacts are unchanged. No synthetic experiment is deleted or regenerated. No model is refitted, and no future evaluation outcomes are used. Two new report replays rebuild observed transformations and exhibits from the same frozen fitted artifacts; release receipts record exact verification rather than claiming a new inference run.

The 12-slide companion and its native charts are retained from v5 because their source figures and numeric exhibits are unchanged; this revision's additional CAC and segmentation teaching is in the report and methodology note. Historical v4 and v5 releases remain available.

Larsen and the course materials join the report's explicit citations and references. The source record in `assets/` distinguishes a citation from redistribution permission. The licensed Orduz notebook and its provenance remain unchanged.


Version 6.0.1 changes only the cover title and layout: the question and Studio North subtitle each occupy one centered line. PDF metadata and the preview match. The 48 following pages and all numerical exhibits retain the v6.0.0 content.


Version 6.0.2 also centers the evidence-period and observation-cutoff lines beneath the two-line title. PDF metadata and the preview match. The 48 following pages and all numerical exhibits retain the v6.0.0 content.


Version 6.1.0 consolidates the recent requirements in the root and report skills and adds a public reproducibility guide. The verifier now has explicit report-replay and full-inference modes, validates the complete evidence chain before comparison, and compares saved SQL and all newer manifests. The implementation fingerprint now includes Python scripts, linked documentation and vendored Archify files. An integrity command validates reference artifacts and preserved companion provenance from an extracted ZIP. The analytical definitions, original data, fits, numerical exhibits and report layout are unchanged; current release receipts distinguish new checks from preserved prior evidence.
