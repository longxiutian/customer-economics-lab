---
name: studio-north-automatic-test
description: Run the explicitly requested November 11 Studio North automatic test through the canonical analysis, executive report, and personal debrief, without guided checkpoint pauses.
---

# Temporary automatic test

The instructor authorized this exception on November 10 for the November 11,
2026 two-student test. Ordinary student requests still use the guided root skill.
Use this mode only when the student explicitly requests the automatic test.
It runs the same frozen eight datasets, models, analytical stages and Version B
report. It does not create `next step` messages or student judgments.

## BlueChip

The targeted service window is November 11, 9:30 a.m.–12:30 p.m. Eastern.
Readiness must be verified live; a scheduled Slurm job is not an online service.
Use the existing authenticated lab API and the student's own workspace. The
student's exact opening message is:

```text
Run the Studio North automatic test and generate my report and personal debrief.
```

Call status first. If ready, automatic_test_available is true, and no run exists,
call start with that actual message, a unique request ID and revision 0. The
broker recognizes this exact request and selects the time-limited automatic mode.
An existing workspace resumes; never reset it or convert a guided run silently.
One analysis job executes all eight stages. Show its returned progress link and
queue status. Refresh the existing job after reconnects; do not create another
run or manufacture checkpoint consent. The broker queues the separate reviewed
debrief when the report completes. Check its existing job until completion.

Deliver the real executive report PDF, editable source, and separate personal
debrief PDF/HTML. The report may be downloaded while the debrief is pending.
Claim full completion only when validation.workflow_complete is true. Preserve
signed links exactly. Explain that the recommendation is analyst-authored and
the automatic run does not demonstrate guided lesson participation.

## Local coding agent

Use the current repository, setup instructions and root skill's analytical and
report requirements. The automatic exception overrides only learner gates.
Save the actual opening request verbatim in `automatic-request.txt` outside the
output directory. Then run:

```text
uv run --frozen python scripts/run_automatic.py --harness Codex --prompt-file automatic-request.txt --output outputs/automatic-test
```

Name the actual harness when it is not Codex. Use a fresh output folder. Preserve
the released seed and at least 3,000 inference steps. Resume only after checking
that the earlier process has stopped; `--resume` verifies source/data/settings
and preserves completed stages. An uncertain hosted job requires operator review.

The runner prepares the local personal-debrief scaffold. Review the actual saved
request, artifacts and recorded usage, then personalize, validate and render it
following [the debrief contract](../../docs/personal-debrief.md). A scaffold alone
is not the finished debrief. Record unknown usage as unknown and label any text
estimate. Do not infer learning from a one-prompt automatic run or pretend that
Opus reviewed it when the current agent performed that review.

Use the shared report generator with its invisible report ID and exact cover
credit: Professor Longxiu Tian / Fall 2026. Never deliver the archived reference
PDF as the new report. Preserve the automatic-run receipt with the final outputs.
