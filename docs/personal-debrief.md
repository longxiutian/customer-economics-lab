# One personal learning debrief across all three execution routes

Every student receives two different artifacts: the Studio North executive report
and a personal debrief about their analysis and use of AI. The latter includes
recorded activity, evidence-linked observations, two Studio North next steps and
two AI-practice next steps, each with a prompt to try. It does not grade learners.

The skill owns this requirement, regardless of who supplies model access:

- **Personal coding agent:** Codex, Claude Code, or an AI agent in VS Code runs the
  repository in a local/cloud workspace. The current agent drafts and checks the
  debrief. Instructor-orchestrated Opus 5.5 high can refine the same evidence packet
  when that authorized service is available; students need not buy separate Opus access.
- **University-funded MCP scenario (TBD):** the same local workflow and debrief,
  with university model calls recorded in their own meter scope. The client's own
  inference remains separate. No connection, funding commitment or unlimited
  Free-account capacity is implied by the proposed design.
- **BlueChip + Longleaf:** the server records authenticated run activity and
  Nemotron receipts; Codex orchestrates Opus 5.5 high using `hosting/student_debrief.py`.
  Native BlueChip usage remains a separate source. Private delivery uses the
  authenticated recipient mapping, never an address inferred from model text.

## Begin logging at the opening

After `student.py start` has created the new output folder, the local agent runs:

```text
uv run --frozen python -m cohort_lab.debrief --output outputs/student init --route personal --harness Codex
```

Use `university_mcp` only for a verified university-funded connection, and the
actual harness name. Preserve that same output folder when resuming. This command
creates a private local run identity; it does not claim to authenticate a UNC login.
The hosted broker remains the authority for hosted identity and delivery.

The opening explains: “I will keep your lab questions, judgments, output references
and available usage records in this workspace so you receive a personal debrief.
I will distinguish measured tokens from estimates and missing information.”

All learner messages already go through `student.py message` unchanged. At each
turn, record the visible assistant reply (and any deliberately captured tool text)
using a stable turn ID. Do not store hidden reasoning or inspect unrelated chats.
Write a JSON file, then call:

```text
uv run --frozen python -m cohort_lab.debrief --output outputs/student record --file reply-record.json
```

```json
{"event_id":"assistant-turn-001","kind":"text","role":"assistant","scope":"lab","text":"The actual reply shown to the learner."}
```

The agent must write the actual reply it presents, not a reconstructed account of
what it thinks happened. A replay with the same ID is idempotent; conflicting text
under that ID is an error. Do not log learner text again as assistant text.

## Measure what the harness exposes; label the rest

Record actual provider/harness receipts when exposed by a supported session export,
usage command, telemetry integration, or authenticated university gateway. Access
only the selected lab session. No background scan of every Codex/Claude conversation
is required or authorized by this skill. Record a source and provider/model for each
stream. Preserve exports separately when the student supplies them.

```json
{"event_id":"provider-response-001","kind":"usage","provider":"openai","model":"actual-model-id","meter_scope":"harness","stream_id":"this-lab-harness-session","mode":"call","source":"selected-session usage receipt","semantics":"openai_inclusive","usage":{"input_tokens":1200,"output_tokens":300}}
```

For a cumulative counter, use `mode: "cumulative"` and a monotonically increasing
`sequence`. Capture a baseline at the start and a final reading for the same model,
scope and stream. Only their difference belongs to this interval. A baseline alone
is unknown usage, not zero. A reset needs a new stream and baseline. Never combine
per-call and cumulative accounting for the same stream or overlap one provider
request across different streams. Keep `harness`, `university_mcp`, `nemotron`
and `debrief` scopes separate; do not add a gateway's bill and a duplicate provider bill.

`openai_inclusive` means input already includes cached input and output already
includes any counted reasoning. `anthropic_input_excludes_cache` requires the
separate `cache_read_input_tokens` and `cache_creation_input_tokens` fields; they
are added to uncached input exactly once. Missing fields remain unknown.

Without receipts, the helper estimates only the recorded text's token volume:
UTF-8 bytes / 4, with a 2–6 bytes/token sensitivity range. This is an explicitly
labeled heuristic, not a confidence interval, full inference-token estimate,
invoice, or fraction of a weekly subscription. Repeated context, hidden reasoning,
system instructions and unrecorded tool traffic are outside it. The full-session
inference total remains unknown. A context-window occupancy display is not a
cumulative usage meter. Do not make up counters to fill a table.

Current primary references: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[Codex plan access](https://learn.chatgpt.com/docs/pricing),
[Claude Code usage and costs](https://code.claude.com/docs/en/costs), and
[VS Code OpenTelemetry](https://code.visualstudio.com/docs/configure/telemetry#_opentelemetry-support-for-agent-interactions).
These describe available product mechanisms; this repository does not silently
install platform-wide telemetry or promise that every student's interface exposes it.

## Finish with the executive report and the learning debrief

The last guided checkpoint prepares a local debrief scaffold automatically when
logging was initialized. It is a fallback, not an Opus-written personal assessment.
The current agent then performs the same evidence/review workflow as the hosted route:

1. Record the final available usage receipts and visible lab replies; run `prepare`
   with the same `--output` prefix. This freezes a new version under `debrief/<snapshot>/`.
2. Read `feedback-request.txt` and `evidence-packet.json`. Draft or refine the
   requested JSON using the current authorized model, or the instructor's available
   Opus 5.5 high service. Review the actual learner questions, saved judgments and
   outputs; do not treat a model's interpretation as a verified numerical result.
3. Save the response as a JSON file, check its claims, and run:

```text
uv run --frozen python -m cohort_lab.debrief --output outputs/student render --snapshot outputs/student/debrief/SNAPSHOT/evidence-packet.json --response reviewed-feedback.json --model ACTUAL_MODEL
```

4. Give the student both the executive-report link and `personal-debrief.html`.
   Include a brief explanation of measured/estimated/unknown usage. Preserve the
   frozen packet and reviewed JSON. Questions after completion do not restart the
   analysis; explicitly refresh a debrief when later activity should be included.

The helper validates same-snapshot citations and exact quotes; the agent checks
their meaning. `render` never calls a provider or sends a message. Student-owned
workspaces deliver locally by default. An instructor collection or central delivery
requires a configured authenticated path; merely creating a packet does not upload it.
