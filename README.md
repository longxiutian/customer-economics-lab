# Customer Economics Lab

**Are we moving in the right direction as a company?**

[Read the eight-page report](examples/reference/report/customer-economics-report.pdf) · [Companion slides: PDF](teaching/customer-economics-lab.pdf) / [PowerPoint](teaching/customer-economics-lab.pptx) · [Stage-gated skill](SKILL.md)

This guided lab begins with eight separate synthetic CSV exports. In one AI-agent chat, students inspect the sources, build cohort summaries with DuckDB SQL, compare acquisition and retention economics, interpret experiments, forecast immature cohorts, and produce a short company report.

The lab is designed around customer economics across successive joining cohorts. It includes clean documented keys, local SQL execution, an Archify system diagram, customer journeys, NumPyro forecasts, and editable LaTeX/PDF output.

![Report preview](examples/reference/report/preview.png)

## Start in Codex

Paste this request into a local Codex chat:

> Download the public repository https://github.com/longxiutian/customer-economics-lab as a ZIP over HTTPS, preferably the v1.0.0 release. Do not install Git or ask me to create a GitHub account. Extract it into a new working folder, read SKILL.md, and help me complete setup. Run the lab one stage at a time. Stop after each stage and wait until I explicitly say “next.”

You can also use GitHub's **Code → Download ZIP**, extract it, and ask Codex to read `SKILL.md` in that folder. The repository does not need to be installed as a global skill. Its bundled supporting diagram package does not require Git either.

Complete [setup](docs/setup.md) before the class. The core requirements are Python 3.12, the frozen `uv.lock` environment, Node 18+, and a supported LaTeX renderer. DuckDB reads the CSVs locally; there is no database server or paid cloud account to configure.

## Guided commands

Run commands from the extracted repository:

```text
uv sync --frozen
uv run --frozen python lab.py start
uv run --frozen python lab.py message "next"
uv run --frozen python lab.py status
```

`start` runs setup only. Each explicit `next` advances one stage. Questions and corrections do not advance. Progress, source hashes, and learner choices live in `outputs/guided/lab_state.json`, so another chat can resume the same folder.

Save your own interpretation without advancing:

```text
uv run --frozen python lab.py choose provisional_verdict "Growth is improving, but the newest cohort is still immature."
```

Changing a judgment invalidates dependent stage records and archives stale outputs. Modified frozen CSVs fail validation; the lab does not silently use them.

After stage 3, ask a natural-language question about the data. Codex can write and execute a single read-only SQL query through the logged helper:

```text
uv run --frozen python lab.py query --sql-file my-question.sql
```

For example, `SELECT cohort_month, n_acquired, cac FROM cohort_six_month_comparison ORDER BY cohort_month` examines comparable older cohorts. The helper saves the exact SQL, input hashes, full bounded result CSV, and receipt under `outputs/guided/queries/`. Questions never advance the guided stage. Writes, external file/network reads, and multiple statements are rejected; oversized results require a narrower query. A verified instructor batch output can be explored with `query --instructor` and the corresponding `--output` option.

## The eight stages

0. Check readiness and understand the company question.
1. Inspect separate source files and draw the system map.
2. Classify UCV fields, propose segments, and map journeys.
3. Build cohort views through saved DuckDB SQL.
4. Compare cohort trajectories, segmentation, and company growth.
5. Check acquisition incrementality with experiments.
6. Forecast immature cohorts and examine LTV/payback.
7. State a supported company verdict and compile the report.

Use the [business brief](docs/business_brief.md), [data dictionary](docs/data_dictionary.md), and [sources](docs/sources.md) as references. The final report separates observed evidence, forecasts, assumptions, and the learner's recommendation.

## Instructor reproducibility

The classroom data release is version **1.0**, generated from seed **20261116**. The source manifest records every CSV's hash and definitions. The canonical pipeline generates the tables; plotting and reporting consume those results.

For an explicitly requested full reproducibility run:

```text
uv run --frozen python lab.py --output outputs/instructor batch --instructor
uv run --frozen python -m pytest
uv run --frozen python scripts/verify_reproducibility.py --output outputs/replay-check
```

Batch mode intentionally runs all computations and is not the student-chat workflow. Choose a fresh empty output folder for each run. Use `--no-pdf` before the command only when an editable TeX result is intentionally sufficient. A different model step budget or seed is recorded and invalidates dependent guided outputs. Changes to core code, SQL, templates, or the frozen environment fail closed in an existing guided session; restore the release or begin a new output folder.

The release uses 3,000 model steps. [Model review and limitations](docs/model-review.md) explains the adversarial checks, the historical valuation backtest, and what the uncertainty bands do and do not establish.

The original code, synthetic data, and teaching materials use the repository's MIT license. Bundled third-party components retain their own licenses. The source articles and tutorials are linked, not copied into the data release.
