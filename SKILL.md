---
name: customer-economics-lab
description: Build an auditable executive customer-economics assessment from separate CSV source systems through DuckDB ETL, cohort analytics, acquisition evidence, retention forecasts, and decisions. Use as a staged single-chat framework that managers can hand to their teams.
---

# Customer Economics Lab

The decision throughout this framework is **Are we moving in the right direction as a company?** Compare successive first-paid acquisition cohorts on retention, contribution, CAC, LTV, and payback. Use segments and channels to explain the trajectory, then connect cohorts to the company in calendar time. The deliverable is an executive assessment and an auditable analytical handoff for the team. Learning happens through inspecting that real workflow; the report must not read like a worksheet or lesson plan.

Open with Studio North's business, revenue model, acquisition channels, customer needs, and management decision. Explain why its eight exports have different owners and grains before introducing software. There are 24 acquisition cohorts, January 2024–December 2025, whose members face monthly renewal decisions. Cohorts share acquisition month; segments share relevant characteristics or needs. These terms are not interchangeable.

## Start and preserve the student's place

1. Work in the downloaded repository. Read [setup](docs/setup.md), [business brief](docs/business_brief.md), and the [data dictionary](docs/data_dictionary.md) as needed. The repository and supporting Archify package work without Git, a GitHub account, or a database server. Public repository archives can be downloaded over HTTPS; never instruct the student to install Git or clone the repository. Do not install this skill globally unless asked.
2. Use the frozen environment: Python 3.12 and `uv sync --frozen`. Node 20+, `npm ci --prefix tools`, and `npx --prefix tools playwright install chromium` provide the bundled Archify diagrams and pinned static-image exporter. A LaTeX engine is required for PDF output. Read the bundled [executive report skill](skills/executive-report/SKILL.md) before drafting: its Source Sans / forest-green / ochre style and source assets are included here. Never require Longxiu's private skill installation. Let setup happen before the class session; report any missing component explicitly.
3. Run `uv run --frozen python lab.py start`. This runs only stage 0. If `outputs/guided/lab_state.json` exists, the command resumes the saved position without rerunning or advancing it.
4. **Stop after every stage.** Show the current artifact, explain what it establishes, identify one check or judgment, and end with **Type next to continue.** Only the student's explicit message `next` authorizes the next stage. Pass their actual message to `uv run --frozen python lab.py message "next"`; it executes exactly one stage. Do not synthesize a `next`, chain several next commands, or treat a question, correction, or answer as permission to advance.
5. For questions, stay in the current stage. `lab.py message "<actual learner message>"` records a question without advancing. Save substantive judgments with `lab.py choose <key> "<learner's judgment>"`. Supported keys are `segmentation_rationale`, `journey_hypothesis`, `provisional_verdict`, `final_verdict`, and `recommended_action`. Do not invent the learner's choice. A changed choice invalidates affected downstream stage records and archives stale artifacts.
6. After interruption or chat compaction, run `lab.py status`, read the saved choices and last stage result, and continue from there. Do not restart the pipeline from memory. A file-integrity error must remain visible: restore the frozen release inputs and begin in a new output folder, rather than silently accepting changed data.

The instructor may explicitly request `lab.py batch --instructor` for reproducibility or regression checks. **Batch mode is never the default in a student chat.** The guided state and exact SQL are part of the lesson.

## Stages and intermediate views

| Stage | Work and artifact | Interpretation before stopping |
|---|---|---|
| 0 | Check environment and data release; introduce the business brief. | Explain the company question, observed cutoff, and common valuation horizon. |
| 1 | Inspect eight separate CSV sources; open `diagrams/source-systems.html`. | Explain the row units, ordinary joins, and the business purpose of each source. This is not an identity-fragmentation puzzle. |
| 2 | Classify Universal Customer View (UCV) **fields**; compare candidate segmentation ideas; open the journey maps. | Create one field-name table per dataset, with columns **Identifiers, Engagement, Relationship, Perception**. Preserve gaps and explain ambiguous assignments. Record a provisional segmentation rationale and a journey hypothesis. Outcome-based heterogeneity is checked after SQL construction, not asserted here. |
| 3 | Run the canonical DuckDB pipeline and display its saved SQL and output tables. | Show one transformation from source rows to a cohort summary, and its reconciliation. SQL runs locally against CSVs; no database service is provisioned. |
| 4 | Open the analysis charts and `segmentation_comparison.csv`. | Compare cohorts at equivalent ages. Check the earlier segmentation rationale on older cohorts; separate changing mix from within-group performance. Ask for a provisional company verdict. |
| 5 | Show experimental assignment summaries and effects. | Keep all assigned prospects, including nonbuyers. Explain what the randomized comparison establishes about acquisition efficiency at its tested scope. |
| 6 | Explain the retention/revenue model and its assumptions; fit it; show validation before forecast curves and LTV/payback. | Separate observed history, forecast tail, and assumptions. Explain persistent customer heterogeneity and survivor selection. Identify exactly what is adapted from Orduz and what differs. The canonical prediction strata remain channel × primary need; descriptive exploration of another grouping does not imply a different fitted model. |
| 7 | Obtain the learner's final verdict and action, then compile the report. | State whether company customer economics are improving, deteriorating, mixed, or still uncertain, with evidence and a condition for revisiting the recommendation. |

At stage 6, ask the learner to state their final verdict and recommended action before they type `next` for stage 7. Save those choices first. The final report must distinguish the learner's judgment from generated evidence. If their interpretation conflicts with the results, discuss that conflict rather than rewriting the evidence to agree.

## Executive report and technical handoff

Read and apply the bundled executive-report skill. The opening page must state the business, management conclusion, quantified evidence, recommended action, and material uncertainty in executive prose. Avoid instructions such as "your task," "discuss," or "what did we learn" in the management report. A question belongs in the guided chat, not in place of a conclusion. Use actual computed results and distinguish an analyst recommendation from the learner's own recorded judgment.

Explain the model before presenting its forecasts: unit of analysis, renewal risk set, heterogeneity, revenue mechanism, censoring, forecast horizon, and uncertainty. Do not present a named package as an explanation of the model. Distinguish the frozen data-generating mechanism from the inference model; never feed latent simulation propensities into the fitted model or regenerate the sources to obtain a more convenient fit.

An appendix is mandatory for a full analytical report. Include estimated parameters with units, priors, uncertainty and interpretation; model assumptions and source adaptations; chronological validation and baseline comparisons; one UCV table per source; source grains/keys and the Archify relationship diagram; and the reproducibility manifest. Complete parameter CSVs and editable SQL/code accompany the report. Keep technical detail out of the opening recommendation without hiding it from the team.

## Evidence rules

- Use the released CSVs unchanged. Do not regenerate a more convenient scenario or substitute handcrafted cohort triangles. The data are original synthetic records, not private course data.
- Cohort means customers whose first successful paid acquisition occurred in the same month. CRM creation, product activity, and experiment assignment are different dates.
- Use the original acquired-customer denominator. Future unobserved ages are missing, not zero. Contractual retention, period-paying customers, orders, and revenue retention are distinct outcomes.
- Keep SQL as the single aggregation path. Use the canonical `cohort_lab.analysis` pipeline; do not create a second pandas calculation that quietly disagrees. After stage 3, translate additional natural-language questions into one SELECT (WITH is supported), show the relevant SQL, save it under the output folder, then run `lab.py query --sql-file <file>`. Keep the canonical repository `sql/` directory unchanged. Read the saved result and explain it; never answer from an unexecuted query. The helper verifies raw/derived inputs, materializes approved tables in memory, disables external access, and saves exact SQL, source hashes, result CSV, and a receipt under `outputs/guided/queries/`. It does not advance the stage. Use the eight raw names (or `raw.<name>`) and canonical analytical table names; model tables become available when their validated outputs exist. Narrow an oversized query rather than silently truncating its result.
- Net revenue deducts discounts and refunds. Contribution also deducts explicit nonmarketing variable costs. Marketing acquisition spending enters CAC and net LTV once. Revenue forecasts alone are not contribution-based LTV.
- Segment CAC requires directly targeted spend or an explicit justified allocation. Do not allocate broad campaign cost according to later revenue and present it as observed segment cost.
- An acquisition experiment includes all assigned eligible prospects and its own control. Attributed cohort LTV and channel differences are not automatically causal marketing effects. Do not multiply incremental buyers by average buyer LTV and label that causal long-run campaign value.
- Judge young cohorts on a common horizon and mark forecasts visibly. Backtests evaluate held-out observed periods; they do not prove the distant tail. Customer economics are not whole-company accounting profit because fixed operating costs are outside this dataset.
- Product logs provide observed events; surveys provide reported perceptions; a journey explanation may remain a hypothesis. Absence of feedback is not a zero rating.

## Packages, outputs, and supporting material

The locked Python environment includes DuckDB, NumPy/pandas, Matplotlib, JAX/NumPyro, and report/test dependencies. Archify is bundled under its own license; Node runs it locally. LaTeX setup is documented separately. Use [sources](docs/sources.md) for the Bouhnick cohort tables, Orduz modeling walkthrough, and McCarthy tutorial. Those are instructional references, not redistributed source datasets.

Keep student-facing prose concise and show the actual intermediate charts/tables. Preserve `lab_state.json`, `learner_choices.json`, SQL, validation receipts, source fingerprints, model outputs, editable report source, and PDF in the output directory. If fitting or PDF compilation fails, report the failed stage and preserve the usable outputs; do not label a reference fit or source-only report as a successful fresh computation.
