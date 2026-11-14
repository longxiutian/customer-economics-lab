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

## Setup and one opening

Use Python 3.12 and uv. From the pinned lab checkout:

```text
uv sync --project api_bridge --frozen --extra keyring
```

If uv's automatically selected interpreter is broken, select an existing Python
3.12 explicitly with `--python ABSOLUTE_PYTHON`; do not replace working system
Python. On Windows use the native Windows environment for the OS credential
store, even when the coding harness can also use WSL.

The agent chooses absolute paths for a fresh output directory and an owner-local
configuration outside the checkout, then runs:

```text
uv run --project api_bridge --frozen --extra keyring python -m unc_sol_bridge connect --config CONFIG --source-root CHECKOUT --run-dir OUTPUT --harness Codex
```

Use `Codex`, `"Claude Code"` or `"VS Code"` for the actual harness. Connection
creates a pending device at the instructor's gateway, saves an opaque credential
in the secure OS keyring, runs `student.py start` and initializes debrief logging.
It does not call a model or send an API key to the student. Open the returned
BlueChip link, sign in with UNC and send `pair CODE` using the printed short
code. Return to the original coding chat and say `done`, then run:

```text
uv run --project api_bridge --frozen --extra keyring python -m unc_sol_bridge pair-status --config CONFIG
```

Continue only when its status is `approved`. Re-running `connect` resumes setup;
it can renew an expired short code without changing the device or usage ledger.
Pair codes expire after 15 minutes;
device authorization lasts 30 days and can be revoked. A secure keyring is
required for this route; there is no plaintext fallback. Unavailable connection
or enrollment checks do not change the native harness or call another provider.

Use a connected native `unc_sol` tool, or the explicit same-chat SDK relay:

```text
uv run --project api_bridge --frozen python -m unc_sol_bridge relay --config CONFIG --tool sol_status
uv run --project api_bridge --frozen python -m unc_sol_bridge relay --config CONFIG --tool sol_preview --arguments OPEN_PREVIEW_JSON
uv run --project api_bridge --frozen python -m unc_sol_bridge relay --config CONFIG --tool sol_ask --arguments OPEN_ASK_JSON
```

`OPEN_PREVIEW_JSON` contains `{"intent":"open"}`.
`OPEN_ASK_JSON` contains `{"request_id":"a-new-unique-id","intent":"open"}`.
These small argument files have no credentials. The relay starts the same local
stdio server using the official MCP SDK, performs one call and closes the child.
Windows children use `pythonw.exe`. It does not bypass the MCP or replace the
native model. It needs no client reload.

Startup permits one dispatched opening, a maximum 5,000-byte combined instruction/
evidence packet, and a 3,000-token output ceiling including reasoning. Its stage
cap is 10,000 tokens. Inspect actual usage and pause at checkpoint 0. Do not install
the full analysis environment, advance readiness or fit models during this test.

## Compact packets and budget accounting

The bridge parses the released lesson definitions, reads the saved checkpoint,
and selects registered artifacts. Tables become bounded rows, dimensions and
numeric ranges; omitted material is identified. Source and implementation hashes
stay in a local manifest. Learner words and judgments are retained literally or
rejected if oversized. The API accepts no transcript, arbitrary file body, system
instructions, previous-response ID, model or endpoint.

Each UNC HTTP request fixes `gpt-6.1-sol`, medium reasoning, non-streaming,
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
accounts for usage across the learner's devices and assigned subscriptions.
Before a request, it can close an allowance with insufficient confirmed
headroom and assign a fresh approved subscription. This happens in the
background; the same chat, files, checkpoint and usage history continue.
Closed allowances are not handed out again as unused. Assignment and accounting
are atomic; overlapping requests cannot claim the same allowance. Subscription
changes never bypass the current 10,000-token, one-opening startup limit.
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

This test release enforces startup-only in code; editing its configuration cannot
enable a full run. A separately verified continuation release will follow
`skills/unc-api/SKILL.md` and retain the same managed identity and ledger. Its designed
normal packet limit is 8,000
bytes (configurable up to 16,000). It does not bypass the nineteen checkpoint
gates. Full analytical dependencies are installed at readiness. All statistical
and PDF work is local and consumes no UNC inference tokens.

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

```text
uv sync --project api_bridge --frozen --extra keyring --group dev
uv run --project api_bridge --frozen python -m pytest api_bridge/tests -q
```

Offline fixtures exercise all nineteen packet shapes, concurrent reservations,
restart/idempotency, missing credentials, forbidden arguments, model mismatch,
timeouts, incomplete responses and real stdio exchanges. They do not establish
the token cost or completion of a live nineteen-checkpoint lab. Keep the live
startup receipt separate from those fixtures.
