# Customer Economics Lab

Use an AI coding agent to turn eight customer-data tables into a recommendation for Studio North, a fictional membership business. You guide the reasoning; the agent handles the code.

## Students: copy and paste this into your AI harness

Open **Codex, Claude Code, or GitHub Copilot in agent mode** with the lab folder supplied for your class session. These tools need access to files and a local or cloud environment where they can run code. Then paste the entire prompt below:

```text
Guide me through the Studio North Customer Economics Lab as a student.

Use the instructor-provided lab folder in this workspace. First check that it
contains both SKILL.md and skills/student-teacher/SKILL.md. If the folder or
either file is missing, stop and help me locate the guided student edition.
Do not substitute an older release or generate the report immediately.

Read both skills. Start with a short introduction to Studio North, the
management question, and our learning roadmap before setting up software.
Help me complete the documented setup, then use student.py for the guided lab.
I should not need to write code, install Git, or create a GitHub account.

At every checkpoint, show the actual intermediate tables, diagrams, or charts
in this chat. Explain what they mean in plain language and invite questions.
Then stop. Advance exactly one checkpoint only when my message is "next step".
A question, an answer, or a revised judgment does not authorize advancement.

Record my own judgments and preserve my place so we can resume later.
Generate the final report only at the last checkpoint, after I have supplied
my recommendation and explicitly said "next step".
```

The guided student package will be distributed for your lab session. Extract that ZIP and open its folder in your agent before starting. Existing tagged releases are archived examples and may not contain the teaching skill. If you have only a browser chat without file and code execution tools, partner with a classmate who has a coding-agent setup.

## What you will do

The lab connects the Universal Customer View and customer journey to SQL cohort construction, segmentation, acquisition incrementality, LTV forecasting, and a management recommendation. Across **19 checkpoints**, your agent shows the evidence as it is produced. The report comes last.

You can ask questions or revise your interpretation at any checkpoint. Say **next step** when you are ready to move on. To resume another day, open the same lab folder and ask your agent to read the student-teacher skill and resume your saved position.

## Before class

Ask your agent to help you complete the [setup guide](docs/setup.md) using your class-session package. The workflow uses a locked Python environment, local SQL, diagram tools, and a PDF renderer. You do not need a database server, GPU, Git installation, or GitHub account.

Useful background: [Studio North business brief](docs/business_brief.md) · [Data dictionary](docs/data_dictionary.md) · [Methods and sources](docs/sources.md).

<details>
<summary>Instructor and technical reference</summary>

The guided edition bundles three skills: the root `SKILL.md` defines the analysis, `skills/student-teacher/SKILL.md` teaches it through explicit checkpoints, and `skills/executive-report/SKILL.md` specifies the final document. The atomic-step audit is in `docs/student-workflow.md` within that package.

The agent runs the following commands from the guided edition's root. Students can use the natural-language prompt above.

```text
uv sync --frozen
uv run --frozen python student.py start
uv run --frozen python student.py message "next step"
uv run --frozen python student.py status
```

`start` opens the introduction only. The first `next step` checks readiness. Progress is saved under `outputs/student/` in `lesson_state.json`, `lab_state.json`, and `learner_choices.json`. Questions and choices never advance the lesson; revised judgments invalidate dependent results. Instructor batch mode is a separate, explicitly requested workflow.

The main model combines heterogeneous-churn shifted-Beta-Geometric retention with Gamma revenue. An adapted Orduz neural model is a separate validation comparison. The public analysis starts from frozen synthetic exports; private data-generation settings and future evaluation outcomes are not distributed. See the [model specification](docs/model-specification.md), [model review](docs/model-review.md), and [reproducibility guide](docs/reproducibility.md).

The latest tagged release is **1.7.0**, an archived reference. The 2026 edition uses 1.x.x; see the [versioning policy](docs/versioning.md). Preserve historical releases and receipts. Validate archived artifacts against their matching source checkout, rather than assuming they were built by the current code.

Current companion slides: [PDF](teaching/Studio-North-Agentic-AI-Lab.pdf) / [PowerPoint](teaching/Studio-North-Agentic-AI-Lab.pptx). This 33-slide edition explains how the report was made and ends with seven reusable FAQ prompts. See [the slide brief and provenance](docs/companion-slides.md).

Archived materials: [1.7.0 example report](examples/reference/report/customer-economics-report.pdf) · [1.7.0 companion slides: PDF](teaching/customer-economics-lab.pdf) / [PowerPoint](teaching/customer-economics-lab.pptx). Use the current materials supplied for your class session.

The original code, synthetic data, and teaching materials use the repository's MIT license. Bundled third-party components retain their own licenses and provenance under `assets/` and `vendor/`.

</details>
