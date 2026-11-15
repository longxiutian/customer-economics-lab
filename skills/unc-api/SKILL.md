---
name: unc-api
description: Run the guided Studio North lab in the current coding-agent chat, delegating teaching to UNC gpt-6.1-sol through compact, budget-guarded MCP calls.
---

# UNC API route

Keep this chat and its native provider. Use the native agent to execute local commands and present evidence; UNC **gpt-6.1-sol** supplies the principal teaching and interpretation. No Luna, provider-profile replacement, full-transcript forwarding or alternate paid fallback. This route retains all nineteen learner-controlled checkpoints.

## Startup test

Read only [the setup commands](../../docs/api-route.md#setup-and-one-opening). Do not read the whole repository into model context. Resolve the instructor's test release to one commit, preserve existing work, and save that identity locally.

1. Use the separate locked environment under `api_bridge/`. Startup needs no analytical packages, Node or LaTeX. Run `connect` locally: it creates an opaque device credential in the secure OS keyring, opens checkpoint 0 and initializes debrief logging. No sign-in, pairing code or API-key entry is needed. The first `sol_ask` registers the device and uses Jev to check the learner's literal starting request before assigning a subscription. This is a check of lab purpose, not verified student identity. An unavailable service is a typed route failure, not a reason to seek another key or change providers. Keep configuration outside Git.
2. Use `sol_status` and `sol_preview(intent="open", learner_text=ACTUAL_STARTING_REQUEST)`. Pass the learner's literal starting request, never an agent-composed substitute; it must fit 4096 UTF-8 bytes and contain no credentials. This text goes separately to Venice-hosted Jev for purpose admission. Sol receives the frozen opening packet. Verify checkpoint, budget and packet size locally; do not claim upstream authentication before the paid response.
3. Make **one** `sol_ask` opening with a unique request ID and the same literal `learner_text`. Use native MCP tools if already connected; otherwise use the documented `relay` command, which calls the same stdio MCP without changing apps or client settings. Jev's admission usage and Sol's teaching usage are separate; a denial does not allocate a student subscription or call Sol. Do not retry an ambiguous result.
4. Present Sol's actual answer. Show actual served model, input/output usage, packet bytes and reservation. Stop at checkpoint 0. This startup phase enforces one dispatched opening and a 10,000-token ceiling; do not enlarge it, change IDs to retry, manually rotate keys, or generate a report.

An unavailable MCP affects this route only. Preserve the typed failure and receipt, explain it briefly and continue unrelated conversation. Unknown dispatched usage stays reserved. A repeated request ID retrieves the old result without another provider call. For a managed connection, an uncertain local result can retrieve the gateway's durable result under the same ID; it never replays inference.

The gateway keeps subscriptions and their keys private. It may assign an unused approved subscription or move to another when confirmed usage plus the next reservation would exceed the current allowance. That change is automatic in the background; preserve the student's workspace, judgments and cumulative usage. Never rotate on a timeout, missing usage, rate limit or ambiguous error. Primary/secondary keys share one allowance. This does not expand the startup gate or unlock the full lesson.

## Guided continuation contract

This test release rejects `pilot` and `full` phases in code. Do not promote it by editing configuration. Await a separately verified guided-continuation release; preserve the same subscription, baseline, state directory and output folder. The remainder defines that continuation's contract, not permission to run it now.

Read [the student-teacher skill](../student-teacher/SKILL.md) and root analytical contract progressively as each checkpoint needs them. Prepare the full frozen analytical environment at readiness, following `docs/setup.md`.

Pass actual learner messages to `student.py message`. Only standalone **next step** advances one checkpoint. Save supplied judgments with `student.py choose`; never invent them. Run `student.py status` before requesting teaching, and present its actual charts/tables. Call `sol_ask(intent="teach")` for the saved checkpoint or `question`/`critique` with the learner's literal words. The bridge selects bounded evidence; never pass a transcript, file body, system prompt, endpoint or model.

Follow [the personal-debrief contract](../../docs/personal-debrief.md). Bridge receipts enter its local usage ledger automatically when initialized; native harness usage remains separate and may be unknown. Record visible assistant replies with stable IDs. At completion prepare the frozen debrief, use `intent="debrief"` for evidence-linked JSON, review it and render with the existing validator. Give both the newly generated executive PDF and personal debrief. No startup result establishes full-lab quota adequacy.
