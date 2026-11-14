---
name: unc-api
description: Run the guided Studio North lab in the current coding-agent chat, delegating teaching to UNC gpt-6.1-sol through compact, budget-guarded MCP calls.
---

# UNC API route

Keep this chat and its native provider. Use the native agent to execute local commands and present evidence; UNC **gpt-6.1-sol** supplies the principal teaching and interpretation. No Luna, provider-profile replacement, full-transcript forwarding or alternate paid fallback. This route retains all nineteen learner-controlled checkpoints.

## Startup test

Read only [the setup commands](../../docs/api-route.md#setup-and-one-opening). Do not read the whole repository into model context. Resolve the instructor's test release to one commit, preserve existing work, and save that identity locally.

1. Use the separate locked environment under `api_bridge/`. Startup needs no analytical packages, Node or LaTeX. The local `prepare` command reads one private credential file, stores its key in the OS keyring, opens the real checkpoint 0 and initializes personal-debrief logging. It never calls a model. The file and configuration belong outside Git. If malformed, use its named missing fields to obtain a corrected record; do not open or print the file in chat.
2. Use `sol_status` and `sol_preview(intent="open")`. Verify the recorded checkpoint, current period, baseline, available budget and packet size. Status/preview are local. Do not claim a key is authenticated before the paid response.
3. Make **one** `sol_ask` opening with a unique request ID. Use native MCP tools if already connected; otherwise use the documented `relay` command, which calls the same stdio MCP without changing apps or client settings.
4. Present Sol's actual answer. Show actual served model, input/output usage, packet bytes and reservation. Stop at checkpoint 0. This startup phase enforces one dispatched opening and a 10,000-token ceiling; do not enlarge it, change IDs to retry, rotate keys, or generate a report.

An unavailable MCP affects this route only. Preserve the typed failure and receipt, explain it briefly and continue unrelated conversation. Unknown dispatched usage stays reserved. A repeated request ID retrieves the old result without another provider call.

## Guided continuation contract

This test release rejects `pilot` and `full` phases in code. Do not promote it by editing configuration. Await a separately verified guided-continuation release; preserve the same subscription, baseline, state directory and output folder. The remainder defines that continuation's contract, not permission to run it now.

Read [the student-teacher skill](../student-teacher/SKILL.md) and root analytical contract progressively as each checkpoint needs them. Prepare the full frozen analytical environment at readiness, following `docs/setup.md`.

Pass actual learner messages to `student.py message`. Only standalone **next step** advances one checkpoint. Save supplied judgments with `student.py choose`; never invent them. Run `student.py status` before requesting teaching, and present its actual charts/tables. Call `sol_ask(intent="teach")` for the saved checkpoint or `question`/`critique` with the learner's literal words. The bridge selects bounded evidence; never pass a transcript, file body, system prompt, endpoint or model.

Follow [the personal-debrief contract](../../docs/personal-debrief.md). Bridge receipts enter its local usage ledger automatically when initialized; native harness usage remains separate and may be unknown. Record visible assistant replies with stable IDs. At completion prepare the frozen debrief, use `intent="debrief"` for evidence-linked JSON, review it and render with the existing validator. Give both the newly generated executive PDF and personal debrief. No startup result establishes full-lab quota adequacy.
