# UNC API route in one chat

Codex, Claude Code or an agent in VS Code runs the released Python, DuckDB,
statistical fits, figures and PDF locally. An optional stdio MCP sends one
checkpoint's evidence to UNC **gpt-6.1-sol** for teaching and interpretation.
The native agent presents the answer and performs authorized local actions.
It keeps its existing sign-in and provider. Its own inference has separate
account limits; this bridge does not pay for that inference.

The API project has its own locked dependencies under `api_bridge/`; the
analytical environment and root lock remain separate. No student model server,
network listener, scheduled task or always-on background process is installed.

## Continue an existing project

You can use UNC model access to build a dashboard, write or debug code, create
interactive charts, explore alternative analyses or improve an existing Studio
North report. Your original report can have been generated with personal tokens.
You stay in the same chat and keep the existing analysis; no lesson restart or
new report is required. Use [this continuation prompt](unc-api-project-prompt.txt).

The coding agent identifies the existing analytical checkout (`CHECKOUT`) and
output folder (`OUTPUT`). It installs the latest `api_bridge/` from a separately
pinned tool checkout (`TOOLS`) if the current bridge lacks `project` intent.
Keep the original analytical release and its fits unchanged. In these examples,
replace the uppercase path labels with actual absolute paths and quote paths
containing spaces. Reuse an existing managed `CONFIG` and its ledger. For a new
connection, run:

```text
uv sync --project TOOLS/api_bridge --frozen --extra keyring
uv run --project TOOLS/api_bridge --frozen --extra keyring python -m unc_sol_bridge connect --config CONFIG --source-root CHECKOUT --run-dir OUTPUT --harness "Claude Code" --project
```

Use the actual harness name. `connect --project` does not start a lesson, refit
models or overwrite an existing personal usage session. Secure device credentials,
automatic server-side subscription assignment and confirmed-headroom rollover
are the same as for the guided route. No student API key or BlueChip step is needed.

Create a small, credential-free argument JSON file, then preview and ask through
the actual MCP relay (or equivalent updated native `unc_sol` tools):

```json
{
  "intent": "project",
  "learner_text": "THE LEARNER'S LITERAL STUDIO NORTH PROJECT REQUEST",
  "artifact_ids": ["tables/cohort_valuation_by_segment.csv", "tables/channel_cac_current.csv"],
  "note": "Brief task context, actual file/schema observations or a focused error excerpt."
}
```

```text
uv run --project TOOLS/api_bridge --frozen --extra keyring python -m unc_sol_bridge relay --config CONFIG --tool sol_preview --arguments PREVIEW_JSON
uv run --project TOOLS/api_bridge --frozen --extra keyring python -m unc_sol_bridge relay --config CONFIG --tool sol_ask --arguments ASK_JSON
```

The ask file adds a unique `request_id`. Pass actual learner words unchanged,
not the placeholder. Sol receives bounded real-table/schema/source excerpts and
can return a concrete plan, code and checks. The native coding agent then writes
and tests the requested dashboard in `OUTPUT/dashboard/`, reporting actual results
in subsequent compact packets as needed. It should complete the requested local
work, rather than simply display code and wait for `next step`. A new project
task is distinct from advancing the guided lab. Static HTML/JS, Python, React and
other local implementations are supported; no particular dashboard framework is
required by the bridge.

The finite artifact registry is [project.json](../api_bridge/admission/project.json).
Alongside those named lab sources and outputs, safe `.py`, `.js`, `.ts`, `.jsx`,
`.tsx`, `.html`, `.css`, `.sql`, `.csv`, `.json`, `.md` and `.txt` files under this
run's `dashboard/` can be excerpted. Absolute paths, traversal, escaping links,
credential files, instructor feedback, usage files and dependency trees are
excluded. Select only files that exist. The learner request is capped at 4096
UTF-8 bytes, the task/error note at 2048, and the entire contract/evidence packet
at 16,000 bytes. Project code has a fixed 6,000-token output ceiling, including
reasoning, fully reserved before dispatch; guided teaching retains 3,000.
All reservation and ambiguous-outcome guards remain. Reuse the request ID to retrieve the original result after a lost
reply; this does not send changed files or repeat inference.

If an earlier session has ended, use the existing local `continue lab` control
before more work; handle pending instructor feedback locally first. Never send
feedback for Jev classification. Project calls do not generate a usage report.
When the learner later ends the session and answers/skips the feedback question,
use the normal personal-debrief workflow, including the additional API receipts.
Work without guided state is honestly labeled project work, not guided completion.

## Setup and one opening

Use Python 3.12 and uv. From the pinned lab checkout:

```text
uv sync --project api_bridge --frozen --extra keyring
```

If uv's automatically selected interpreter is broken, select an existing Python
3.12 explicitly with `--python ABSOLUTE_PYTHON`; do not replace working system
Python. On Windows use native Windows Python and the OS credential store. Keep the
bridge in the same native operating environment as the coding harness.

The agent chooses absolute paths for a fresh output directory and an owner-local
configuration outside the checkout, then runs:

```text
uv run --project api_bridge --frozen --extra keyring python -m unc_sol_bridge connect --config CONFIG --source-root CHECKOUT --run-dir OUTPUT --harness Codex
```

Use `Codex`, `"Claude Code"` or `"VS Code"` for the actual harness. Preparation
is entirely local: create a random device credential in the secure OS keyring,
run `student.py start`, and initialize debrief logging. Re-running `connect`
resumes that configuration. The first opening registers the device automatically;
no separate sign-in, pairing code, student name or API-key entry is needed.
The device credential lasts 30 days and can be revoked. A secure keyring is
required; there is no plaintext fallback. This device identifies a saved
connection, not a verified person or enrollment.

Use a connected native `unc_sol` tool, or the explicit same-chat SDK relay:

```text
uv run --project api_bridge --frozen python -m unc_sol_bridge relay --config CONFIG --tool sol_status
uv run --project api_bridge --frozen python -m unc_sol_bridge relay --config CONFIG --tool sol_preview --arguments OPEN_PREVIEW_JSON
uv run --project api_bridge --frozen python -m unc_sol_bridge relay --config CONFIG --tool sol_ask --arguments OPEN_ASK_JSON
```

`OPEN_PREVIEW_JSON` contains `{"intent":"open","learner_text":"THE LITERAL STARTING REQUEST"}`.
`OPEN_ASK_JSON` contains the same literal text plus a unique `request_id`.
Use the actual student message, not the placeholder or an agent-composed request.
The starting request must fit 4096 UTF-8 bytes; oversized text is rejected, never
silently truncated. It is sent separately to Venice-hosted **Jev** for two typed
judgments: lab purpose and an explicit request to bypass access rules. The
gateway applies the frozen policy in `api_bridge/admission/relevance-policy.json`.
An uncertain, rejected or unavailable check does not allocate a student key or
call Sol. No alternate classifier is called. The opening packet sent to Sol
must match the released hash exactly; the literal starting request cannot
override its instructions. Both stages have durable request IDs and separate
usage receipts. Repeat IDs retrieve results without repeating either inference.
These small argument files have no credentials. The relay starts the same local
stdio server using the official MCP SDK, performs one call and closes the child.
Windows children use `pythonw.exe`. It does not bypass the MCP or replace the
native model. It needs no client reload.

The managed connection uses the full guided phase, with a maximum 16,000-byte
combined instruction/evidence packet and a 3,000-token output ceiling including
reasoning. After the opening, wait for the learner's next step. Prepare the full
analytical environment at readiness; never advance all checkpoints automatically.
Legacy startup-only configurations retain their one-opening, 10,000-token guard.

## Compact packets and budget accounting

The bridge parses the released lesson definitions, reads the saved checkpoint,
and selects registered artifacts. Tables become bounded rows, dimensions and
numeric ranges; omitted material is identified. Source and implementation hashes
stay in a local manifest. Learner words and judgments are retained literally or
rejected if oversized. The API accepts no transcript, arbitrary file body, system
instructions, previous-response ID, model or endpoint.

Each teaching HTTP request fixes `gpt-6.1-sol`, medium reasoning, non-streaming,
`store=false`, no tools and no retries. It refuses redirects. A different served
model is rejected and quarantines the allocation.

Before HTTP, a SQLite transaction admits:

```text
declared prior usage + settled usage + outstanding reservations
+ next input byte-bound + framing reserve + output ceiling <= allocation cap
```

The byte-bound reserves one token per UTF-8 byte plus 200 framing tokens; it is
conservative rather than an exact tokenizer measurement. Reported usage settles
the call, counting inclusive input/output once. An actual overrun quarantines
future calls. Concurrent processes share the same owner-local ledger.

Each subscription has at most 400,000 combined tokens. The managed gateway
accounts for usage across the saved device connection's assigned subscriptions.
Before a request, it can close an allowance with insufficient confirmed
headroom and assign a fresh approved subscription. This happens in the
background; the same chat, files, checkpoint and usage history continue.
Closed allowances are not handed out again as unused. Assignment and accounting
are atomic; overlapping requests cannot claim the same allowance. Subscription
changes preserve the local phase guard and all learner-controlled checkpoint gates.
UNC's upstream quota remains authoritative; pool baselines must include any use
outside this gateway. Expired accounting periods cannot dispatch new calls.

Timeout, cancellation or missing usage holds the reservation. A run with unknown
usage cannot send another call until reconciled. Rate limits, authentication
failures and ambiguous errors never switch subscriptions. No reactive UNC quota
error signature has yet been verified, so current rollover uses ledger headroom
only. An existing request ID retrieves its saved result; it never repeats model
inference. Budget and phase denials happen before any provider request.

Legacy instructor tests may still use `prepare --credential-file PRIVATE_RECORD`
with one privately supplied subscription. That route retains its original local
400,000-token cap and cannot participate in automatic pool rollover. Do not
collect or paste credentials for the managed student route.

## Continue the lesson

Follow `skills/unc-api/SKILL.md` for all nineteen checkpoints. New managed
connections use explicit 16,000-byte packets. Save and forward the learner's
actual messages, and send `learner_text=ACTUAL_NEXT_STEP` with a teach request
only after the local checkpoint advanced. Questions and critiques retain their
literal text, capped at 1200 UTF-8 bytes. A registry validates the fixed teaching
frame and registered artifacts at the gateway; it attests to scope and budget,
not remote observation of local fits or verified student identity.

Full analytical dependencies are installed at readiness. All statistical and
PDF work is local and consumes no UNC inference tokens. Deliver the report at
checkpoint 18 and keep questions open. A further next step is a local no-op.
Only end lab or end simulation begins closing; ask exactly Any feedback to
Professor Tian? and wait for a reply or skip feedback. Then prepare and validate
the separate usage/learning debrief. Instructor feedback is collected separately
by the private broker with a stable lab identifier, excluded from both Jev and
Sol. The standard-library feedback helper needs no MCP or model call. For the debrief call, pass the saved literal end command
as learner_text. An early ending can produce a partial-session debrief.

Each call saves `sol_bridge/REQUEST.json`, its delivered text and a usage log in
the student's output folder. Initialized debrief logging receives actual UNC
usage automatically. Native harness receipts and text-volume estimates stay
separate. The final debrief intent uses the released JSON rubric and the student's
actual frozen evidence packet, with IDs preserved for validation.

## Optional native tool registration

`templates --config CONFIG --out DIRECTORY` creates complete Codex TOML,
Claude Code JSON and VS Code JSON definitions. `install` adds only this server
to an explicitly named client configuration, backs it up first and refuses a
conflicting definition. Validate the complete client configuration using that
client before reconnecting. Codex definitions explicitly use `required=false`.
Do not change native provider or authentication settings. The SDK relay avoids
registration when a chat cannot load a new tool immediately.

## Verification

The measured startup receipt is published separately under
[`api_bridge/acceptance/startup.json`](../api_bridge/acceptance/startup.json).
It is not an analytical input or a reference answer for students.
Managed assignment has its own [acceptance record](../api_bridge/acceptance/managed-assignment.json),
which distinguishes offline concurrency and rollover tests from live connection
and student-account checks. A successful connection alone does not establish a
completed lesson or report.
The [Jev calibration receipt](../api_bridge/admission/live-calibration.json)
records the tested policy and representative production-shaped cases.

```text
uv sync --project api_bridge --frozen --extra keyring --group dev
uv run --project api_bridge --frozen python -m pytest api_bridge/tests -q
```

Offline fixtures exercise all nineteen packet shapes, concurrent reservations,
restart/idempotency, missing credentials, forbidden arguments, model mismatch,
timeouts, incomplete responses and real stdio exchanges. They do not establish
the token cost or completion of a live nineteen-checkpoint lab. Keep the live
startup receipt separate from those fixtures.
