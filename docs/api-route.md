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

The instructor supplies **one private credential record**, outside the checkout.
It contains `subscription`, `period_id` (current UTC YYYY-MM),
`baseline_tokens`, `baseline_source` and `primary_key`. Never print its values
or include it in Git, chat prompts or generated reports. The primary and secondary
key of a subscription share its quota; do not rotate between them.
Automatic key distribution is not implemented in this pilot.

The agent chooses absolute paths for a fresh output directory and an owner-local
configuration outside the checkout, then runs:

```text
uv run --project api_bridge --frozen --extra keyring python -m unc_sol_bridge prepare --config CONFIG --source-root CHECKOUT --run-dir OUTPUT --credential-file PRIVATE_RECORD --harness Codex
```

Replace `Codex` with the actual harness name. Preparation does only local work:
validate metadata, save the key in the OS keyring, run `student.py start`, and
initialize debrief logging. If a secure keyring backend is unavailable it fails
before a provider call; environment references are a separate supported
configuration for clients whose private environment is already provisioned.

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

The allocation cap is at most 400,000 combined tokens. This local guard cannot
discover usage from another device or application: provide an honest prior-use
baseline and retain its source. Keep the same state directory on resume; moving
to another machine needs a reconciled baseline. UNC's upstream quota remains
authoritative. A past or future month cannot be used for a new dispatch.

Timeout, cancellation or missing usage holds the reservation. A run with unknown
usage cannot send another call until reconciled. Auth/quota failures are not a
reason to switch keys. A duplicate ID never sends HTTP again. Budget and phase
denials happen before any provider request.

## Continue the lesson

This test release enforces startup-only in code; editing its configuration cannot
enable a full run. A separately verified continuation release will follow
`skills/unc-api/SKILL.md` and retain the same allocation and ledger. Its designed
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

```text
uv sync --project api_bridge --frozen --extra keyring --group dev
uv run --project api_bridge --frozen python -m pytest api_bridge/tests -q
```

Offline fixtures exercise all nineteen packet shapes, concurrent reservations,
restart/idempotency, missing credentials, forbidden arguments, model mismatch,
timeouts, incomplete responses and real stdio exchanges. They do not establish
the token cost or completion of a live nineteen-checkpoint lab. Keep the live
startup receipt separate from those fixtures.
