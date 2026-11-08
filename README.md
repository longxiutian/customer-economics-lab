# Customer Economics Lab

Use AI to turn eight customer-data tables into a recommendation for Studio North, a fictional membership business. You guide the reasoning; the connected computation environment handles the code.

## Choose the route supplied for your session

All three scenarios use the same guided skill and end with an executive report **and your personal learning debrief**. The instructor will confirm which routes are available for class.

| Scenario | Where you work | Model access |
| --- | --- | --- |
| [Personal coding agent](#personal-coding-agent-copy-and-paste-into-your-ai-harness) | Codex, Claude Code, or VS Code with an agent and a local/cloud lab folder | Your supported plan or API account |
| University-funded MCP — **TBD** | A coding agent connected to a proposed UNC model service | Funding, sign-in and free-client suitability still need confirmation |
| [BlueChip + Longleaf](#browser-scenario-bluechip--longleaf) | BlueChip in your browser; the backend runs the lab | Instructor-provisioned Nemotron service during the announced window |

An MCP connection supplies tools and services; it does not automatically fund the coding agent's own model calls. See [execution paths](docs/execution-paths.md) for the exact distinction and [personal debriefs](docs/personal-debrief.md) for what each route records.

## Browser scenario: BlueChip + Longleaf

The BlueChip pilot runs the guided lab through one browser link. No student installation is needed. BlueChip presents the lesson; an instructor-managed backend saves your own workspace, runs fresh CPU models, and obtains Nemotron interpretations.

You can ask how the report is generated and where its data, skills, reference assets, DuckDB calculations and outputs live. The agent retrieves a verified description of the current deployment and explains server-side paths separately from your available downloads. The hosted API supports the released workflow and bounded SQL exploration; implementing alternative models or rewriting chart code remains an exercise for the optional coding-agent route.

**November 7 pilot has ended.** The rehearsal used [Studio North in BlueChip](https://bluechip.kenan-flagler.unc.edu/chat/959a9b88-8e0a-4598-ba27-f8f2e6cfe602): sign in with your UNC BlueChip account, then click **Start my Studio North lab**. Its debugging window ended at **5:15 p.m. Eastern on November 7, 2026**. Use this route only after the instructor announces an active service window. Two API rehearsals and one browser rehearsal produced matching reports with fresh fits. The browser run required a checkpoint-display recovery; see the acceptance record for the remaining interface checks. The instructor confirms MBA and MSM BlueChip access; another student's end-to-end use of this agent and whole-class capacity still need testing; November 16 provisioning is separate. See the [BlueChip setup and acceptance record](docs/bluechip-classroom.md).

In the configured BlueChip agent, paste:

```text
Start or resume my Studio North lab. Check the real service and my saved
workspace. Introduce the current checkpoint, show its evidence, and wait.
Advance one checkpoint only when my whole message is "next step".
```

<details>
<summary>Earlier connection experiment: personal browser ChatGPT (not released)</summary>

The classroom starting point is **your personal ChatGPT account and UNC network access**. The planned lab connection runs the software centrally, gives each student a separate workspace, and runs each student's own statistical fits. You are not expected to install Python, Git, a coding agent, or a tunnel client, buy a paid plan, or obtain an API key or Longleaf account.

**Connection status: being prepared; not yet ready for class.** The instructor will provide the verified plugin link and sign-in instructions. Personal-account access, including Free accounts, must be tested before this route is released. The working local workflow in this repository and the personal model pilot do not yet constitute the hosted classroom service.

After the instructor supplies the working connection, open a new ChatGPT conversation, select the lab plugin, and paste the [browser student prompt](docs/chatgpt-web-student-prompt.txt). It checks the actual connection before starting. A prompt alone cannot connect ChatGPT to UNC.

```text
Use the connected UNC Studio North Lab plugin to guide me through the lab.
First verify the actual connection, pinned release, my authenticated workspace,
and tools for saved lesson state, fresh fits and report downloads. If any are
missing, explain what is missing and stop; do not simulate execution.

Start or resume my own workspace. Introduce the assignment, show my current
checkpoint, and wait. Advance one checkpoint only when my entire message is
"next step". Questions and judgments do not advance the lesson. Show the actual
intermediate outputs and invite my interpretation at every step.

Use UNC Nemotron to interpret the returned evidence and label its responses.
Run my own fresh CPU fit at the fitting checkpoint, preserving the released
settings and the same job ID through retries. Save my actual judgments.
Generate and validate my report only at the final checkpoint after my final
verdict and action, then give me the real download returned by the service.
```

The [classroom access plan](docs/chatgpt-web-classroom.md) records the required connection, student isolation, fresh fits, and readiness checks. This earlier browser-plugin plan is distinct from the proposed university-funded coding-agent MCP route.

</details>

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

The latest tagged release is **1.7.0**, an archived reference. The 2026 edition uses 1.x.x; see the [versioning policy](docs/versioning.md). Preserve historical releases and receipts. Validate archived artifacts against their matching source checkout, rather than assuming they were built by the current code.

Current companion slides: [PDF](teaching/Studio-North-Agentic-AI-Lab.pdf) / [PowerPoint](teaching/Studio-North-Agentic-AI-Lab.pptx). This 33-slide edition explains how the report was made and ends with seven reusable FAQ prompts. See [the slide brief and provenance](docs/companion-slides.md).

Archived materials: [1.7.0 example report](examples/reference/report/customer-economics-report.pdf) · [1.7.0 companion slides: PDF](teaching/customer-economics-lab.pdf) / [PowerPoint](teaching/customer-economics-lab.pptx). Use the current materials supplied for your class session.

The original code, synthetic data, and teaching materials use the repository's MIT license. Bundled third-party components retain their own licenses and provenance under `assets/` and `vendor/`.

</details>
