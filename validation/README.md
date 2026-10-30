# Cover update — v6.0.2

The cover now contains exactly two centered lines: **Are We Moving in the Right Direction?** and **A customer-base analysis of cohort-based LTV at Studio North**. The evidence-period and observation-cutoff lines are also centered. PDF metadata matches. The report remains 49 pages with zero overfull boxes. All 48 following pages are pixel-identical to v6.0.0 at 110 dpi, all 39 numeric tables are unchanged, and all fitted/input manifests validate. Six existing affected tests passed in 2.91 seconds. See `cover-update.json` for measured text bounds and exact scope. The original full-suite and two-replay evidence below retains its v6.0.0 scope.

# Cover update — v6.0.1

The cover now contains exactly two centered lines: **Are We Moving in the Right Direction?** and **A customer-base analysis of cohort-based LTV at Studio North**. PDF metadata matches. The report remains 49 pages with zero overfull boxes. All 48 following pages are pixel-identical to v6.0.0 at 110 dpi, all 39 numeric tables are unchanged, and all fitted/input manifests validate. Six existing affected tests passed in 1.51 seconds. See `cover-update.json` for measured text bounds and exact scope. The original full-suite and two-replay evidence below retains its v6.0.0 scope.

# Release validation — v6.0.0

All **187 collected tests are verified across the full and corrective runs**, including six new independent arithmetic counterexamples. The initial full run passed 186 tests in 1052.82 seconds and failed one stale assertion that expected the v5 download URL. Only that expected URL was updated to v6; no executable code changed afterward. The final workflow suite passed all **21 tests in 10.27 seconds**, including the corrected test. Exact output is in `pytest.txt`.

A separate integration check queries both new derived tables through the real logged SQL helper, verifies that questions do not advance a stage, rejects a tampered decision table and archives the new manifest and tables during stage-4 invalidation. See `decision-metrics-integration.json`.

Two fresh same-host processes rebuilt observed SQL, diagnostics, decision metrics, post-estimation, diagrams and the final PDF using verified frozen fitted artifacts. **125 canonical artifacts are byte-identical**. All **37 prior numeric CSVs** and **55 protected source/fitted artifacts** are unchanged. No model was refitted for this release and no future evaluation outcomes were used or scored. Cross-platform byte equality is not asserted.

The report has **49 pages, 17 figures, 32 tables**, nine section separators, one A3 foldout and otherwise Letter pages. Compilation reports zero overfull boxes. All pages were rendered and reviewed as a contact sheet; cover, contents, summary, segmentation, acquisition-cost and references pages were also inspected at full size. Seven citation keys have matching reference anchors. The cover credit, customer-journey heading, model-after-company order and removed-sentence requirement remain intact. Exact visual scope is in `visual-qa.json`.

Claude Opus 5.5 completed a maximum-effort critique of the supplied methodological design and verified input facts. It did not inspect the full repository or final PDF. Its matched-estimand, horizon, uncertainty, pooling and segmentation clarifications were adjudicated and incorporated; source, arithmetic, integration and rendering checks were performed locally. The small SD discrepancy noted from rounded prompt inputs is absent in the unrounded population-variance reconciliation.

The 12-slide companion and its native charts are unchanged from v5. The licensed Orduz asset is unchanged. Larsen and the course materials are cited; their PDFs are not redistributed. Historical v4/v5 validation remains in the corresponding tags; the older `guided-flow.json` and `post-review-pytest.txt` retain their stated v5 scope rather than being presented as new runs.

A source ZIP was installed into a fresh folder without Git and all frozen data and analytical manifests validated, including decision metrics. The actual public release ZIP and assets receive a separate post-publication download check. Sanitized publication-boundary results are in `private-boundary.json`; private provider transcripts, course-context retrieval and instructor materials remain outside the repository.
