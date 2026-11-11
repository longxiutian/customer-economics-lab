# Customer Economics Lab

Use AI to turn eight customer-data tables into a recommendation for Studio North, a fictional membership business. You guide the reasoning; the connected computation environment handles the code.

**The student edition is interactive only.** Your AI shows the evidence and waits at every checkpoint. It advances one step when you say **next step**, and produces the report after your own final recommendation.

## Choose the route supplied for your session

All three scenarios use the same guided skill and end with an executive report **and your personal learning debrief**. The instructor will confirm which routes are available for class.

| Scenario | Where you work | Model access |
| --- | --- | --- |
| [Personal coding agent](#personal-coding-agent-copy-and-paste-into-your-ai-harness) | Codex, Claude Code, or VS Code with an agent and a local/cloud lab folder | Your supported plan or API account |
| University-funded MCP — **TBD** | A coding agent connected to a proposed UNC model service | Funding, sign-in and free-client suitability still need confirmation |
| [BlueChip + Longleaf](#browser-scenario-bluechip--longleaf) | BlueChip in your browser; the backend runs the lab | Instructor-provisioned Nemotron service during the announced window |

An MCP connection supplies tools and services; it does not automatically fund the coding agent's own model calls. See [execution paths](docs/execution-paths.md) for the exact distinction and [personal debriefs](docs/personal-debrief.md) for what each route records.

## Browser scenario: BlueChip + Longleaf

Use BlueChip during the service window announced for your session. You need your UNC BlueChip account and a web browser. Nothing needs to be installed.

1. Open [Studio North in BlueChip](https://bluechip.kenan-flagler.unc.edu/chat/959a9b88-8e0a-4598-ba27-f8f2e6cfe602) and sign in with your UNC account.
2. Click **Start my Studio North lab**, or paste: `Start or resume my Studio North lab.`
3. At each checkpoint, review the tables, diagrams or charts, ask questions, and share your interpretation. Type **next step** when you are ready to continue.
4. While a calculation runs, open the **live progress** link to see its status. Type **check progress** in BlueChip to retrieve the result.
5. At the final checkpoint, give your recommendation for Studio North, then type **next step** to generate your report.
6. Download your **executive report** and **personal learning debrief** before the service window closes. The debrief may finish after the report; use **check progress** to retrieve its download links.

Your work is saved to your own workspace. Return with the same BlueChip account and ask to resume your lab to continue from your saved checkpoint.

You can also ask how the analysis works. For example:

> Walk me through how the eight datasets, SKILL.md, reference assets, DuckDB SQL, models and figures become this report. Explain where my results are saved and which files I can download.

For projects that change the model or chart code, use the [personal coding-agent route](#personal-coding-agent-copy-and-paste-into-your-ai-harness) below.

## Personal coding agent: copy and paste into your AI harness

Open **Codex, Claude Code, or GitHub Copilot in agent mode** in a local or cloud workspace where it can retrieve files and run code. Paste the entire prompt below; the agent retrieves the lab for you. You do not need to manually download a ZIP, install Git, or create a GitHub account.

```text
Guide me through the Studio North Customer Economics Lab as a student.

Use https://github.com/longxiutian/customer-economics-lab . If this workspace
already contains my lab, preserve it and resume its recorded release. Otherwise,
retrieve the instructor-specified release into a new lab folder. If no release
was specified, resolve the current main branch once to its full commit SHA,
download that exact revision, and save the SHA and source URL in the workspace.
Use the public repository archive if Git is unavailable; do not ask me to
manually download files, install Git, or create a GitHub account.

Check that the retrieved folder contains SKILL.md and
skills/student-teacher/SKILL.md. If retrieval, execution access or either skill
is unavailable, explain what is missing and stop. Do not substitute an older
release, overwrite an existing lab, or generate the report immediately.

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

Follow docs/personal-debrief.md from the opening. Keep my actual questions,
visible replies, judgments and output references. Record available model-usage
receipts; otherwise label an estimate of recorded text and leave full usage
unknown. At the end, give me the executive report AND a personal learning debrief
with evidence-linked Studio North and AI-practice next prompts.
```

The agent retrieves and records one exact revision before setup. If the instructor supplied a guided ZIP or an existing lab folder, it can use that edition instead. Older tagged releases may not contain the teaching skill, so the agent checks before proceeding. This coding-agent setup is separate from the BlueChip browser route.

## What you will do

The lab connects the Universal Customer View and customer journey to SQL cohort construction, segmentation, acquisition incrementality, LTV forecasting, and a management recommendation. Across **19 checkpoints**, your agent shows the evidence as it is produced. The report comes last.

You can ask questions or revise your interpretation at any checkpoint. Say **next step** when you are ready to move on. The browser service must resume your saved position through your authenticated account. For the optional local route, reopen the same lab folder and ask your agent to read the student-teacher skill and resume.

## Before class

For the browser route, complete the instructor's connection check when it is released. The [setup guide](docs/setup.md) is for the backend operator and students who explicitly choose local execution. The backend supplies the locked Python environment, SQL, diagram tools, and PDF renderer.

Useful background: [Studio North business brief](docs/business_brief.md) · [Data dictionary](docs/data_dictionary.md) · [Methods and sources](docs/sources.md).

<details>
<summary>Instructor and technical reference</summary>

The guided edition uses three core skills: the root `SKILL.md` defines the analysis, `skills/student-teacher/SKILL.md` teaches it through explicit checkpoints, and `skills/executive-report/SKILL.md` specifies the final document. The atomic-step audit is in `docs/student-workflow.md`. A separate deferred challenge skill is loaded only for an explicitly requested modeling extension after the lesson.

The agent runs the following commands from the guided edition's root. Students can use the natural-language prompt above.

```text
uv sync --frozen
uv run --frozen python student.py start
uv run --frozen python student.py message "next step"
uv run --frozen python student.py status
```

`start` opens the introduction only. The first `next step` checks readiness. Progress is saved under `outputs/student/` in `lesson_state.json`, `lab_state.json`, and `learner_choices.json`. Questions and choices never advance the lesson; revised judgments invalidate dependent results. Once-through instructor orchestration is outside the current student distribution.

The main model combines heterogeneous-churn shifted-Beta-Geometric retention with Gamma revenue. An adapted Orduz neural model is a separate validation comparison. The public analysis starts from frozen synthetic exports; private data-generation settings and future evaluation outcomes are not distributed. See the [model specification](docs/model-specification.md), [model review](docs/model-review.md), and [reproducibility guide](docs/reproducibility.md).

Use the guided edition retrieved by the prompt above, pinned to its recorded commit. Earlier release downloads containing the batch shortcut are hidden from the student release list. Historical tags and receipts remain for provenance; see the [versioning policy](docs/versioning.md).

Current companion slides: [PDF](teaching/Studio-North-Agentic-AI-Lab.pdf) / [PowerPoint](teaching/Studio-North-Agentic-AI-Lab.pptx). This 33-slide edition explains how the report was made and ends with seven reusable FAQ prompts. See [the slide brief and provenance](docs/companion-slides.md).

The original code, synthetic data, and teaching materials use the repository's MIT license. Bundled third-party components retain their own licenses and provenance under `assets/` and `vendor/`.

</details>
