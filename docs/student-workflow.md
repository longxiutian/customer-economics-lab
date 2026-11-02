# Student workflow and atomicity audit

The student-facing skill is [`skills/student-teacher/SKILL.md`](../skills/student-teacher/SKILL.md). It teaches the root analytical skill through `student.py`. The root skill remains the method contract, and the executive-report skill controls the final document. This is a teaching interface over the same calculations, not a second analysis.

The audit found that the original eight computational stages combined several learning objectives: stage 1 combined business, sources and architecture; stage 2 combined UCV and segmentation; stage 4 combined cohort, segment, journey and company evidence; stage 6 combined model explanation, estimation, validation, value and decisions. Those computations remain reusable, while the student interface separates their interpretation into 19 checkpoints. A checkpoint may reuse previously computed tables; no future report is compiled in the background.

| Step | Single teaching objective | Show before pausing | Canonical computation stage |
|---|---|---|---|
| 0 | Understand the assignment | Business introduction and roadmap | None |
| 1 | Establish readiness | Actual dependency/data checks | 0 |
| 2 | Understand the journey | Broad Studio North journey map | 1 |
| 3 | Understand source grains and joins | Eight-table inventory and relationship map | Reuse 1 |
| 4 | Apply the UCV | Eight field-level UCV tables | 2 |
| 5 | Propose a baseline grouping | Actual profile fields; learner rationale and journey hypothesis | Reuse 2 |
| 6 | Construct a cohort view | Canonical SQL, customer-month rows, cohort aggregate and logged cell-trace query | 3 |
| 7 | Compare retention fairly | Retention triangle | 4 |
| 8 | Explain cohort cash recovery | Cash triangle | Reuse 4 |
| 9 | Assess segmentation | Within/across-cell dispersion and comparison tables | Reuse 4 |
| 10 | Examine journey friction | Journey diagnostics and contrast table | Reuse 4 |
| 11 | Assess company direction | Calendar-time economics and matched-age comparison; provisional verdict | Reuse 4 |
| 12 | Reconcile acquisition cost | Six holdout waves, current iCAC table and history chart | 5 |
| 13 | Understand forecasting assumptions | Model specification and observed/forecast distinction | Reuse 5; no fit yet |
| 14 | Evaluate fitted models | Inference diagnostics and historical validation tables | 6 |
| 15 | Interpret value and payback | Forecast detail and segment valuation | Reuse 6 |
| 16 | Allocate acquisition spending | Value-before-CAC versus current iCAC; cash-recovery path | Reuse 6 |
| 17 | Make a recommendation | Learner's final verdict and recommended action | Reuse 6 |
| 18 | Produce the deliverable | PDF/TeX, source evidence and provenance | 7 |

Every transition requires one actual standalone `next step`. Case and surrounding whitespace do not matter; other messages, questions, choice updates and resume commands cannot advance. Readiness failure retries the same pending checkpoint. Missing final judgment blocks report compilation. Revised choices rewind the affected lessons along with computational invalidation. Instructor batch mode remains an explicit separate path.

`lesson_state.json` records position, messages, evidence references and invalidations. `lab_state.json` retains the eight-stage computational record. The snapshot includes all three skills and both CLI entry points, so a report can identify the teaching and computational instructions used. Frozen inputs and completed results are not silently relabeled after source changes.

Behavioral checks are in `tests/test_student_workflow.py` and the existing computational workflow tests. They cover exact consent, one-step advancement, questions, resume, failure/retry, revisions, final judgment and the absence of a report before the final checkpoint. CLI smoke checks and rendered report QA supplement these tests; they do not establish that every coding-agent interface or operating system has been exercised.
