# BlueChip, Longleaf and personal lab workspaces

Status as of November 7, 2026: the single-GPU instructor rehearsal is verified.
The four-replica router and telemetry/debrief modules are a tested local prototype,
not a deployed four-GPU classroom service. The frozen rehearsal release is unchanged.

## The roles students should understand

BlueChip supplies the browser chat, organization sign-in and API tool calls.
Its interface model is separate from Nemotron. Students do not install a database,
Python, a tunnel client, or a GPU runtime on their laptops.

The authenticated broker links the platform-supplied login to a private run ID.
It enforces workspace ownership, checkpoint revision and one active lesson job.
Its D1 records hold progress and jobs; R2 holds uploaded artifact copies.
Only the exact signed links returned for that run are downloadable artifacts.

The analysis worker reads the eight frozen CSVs, runs DuckDB SQL, fits the
statistical models on CPU with JAX/NumPyro, generates charts and Archify diagrams,
and compiles the report with TeX. The rehearsal used one serial Windows worker.
Each run has separate choices, intermediate tables, fitted outputs and report files.
Source data and pinned code can be shared read-only. Student outputs cannot.

Longleaf serves Nemotron to interpret the computed checkpoint evidence.
The verified baseline uses one RTX PRO 6000 Blackwell Server Edition, 96 GB,
and NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 at revision
`da5b2650a835292c678994a1fa3fb653250fb508`.
GPU memory holds model weights and temporary generation state, not the durable
student workspace. A different GPU can answer a later question from the same run.

## Four independent replicas and one fair router

The classroom design uses four complete, independent single-GPU servers.
Each has its own process, endpoint, admission limit and allocation expiry.
It is not one model split across four cards. Do not substitute vLLM's synchronized
MoE data-parallel group for independent replicas without a separate assessment.

`hosting/inference_router.py` persists the inference queue and physical attempts.
It serves the least recently served student, FIFO within that student's queue,
with at most one active request per student and a bounded pending queue.
It selects the least loaded healthy replica, accounting for its configured capacity.
Stale health, wrong revision/manifest/profile and insufficient remaining lifetime
prevent dispatch. A potentially dispatched timeout stays uncertain; it is not
automatically replayed on another GPU. Reconciliation belongs to the operator.

`hosting/nemotron_router.py --serve` is the single background owner. It uses an
exclusive local lease and an ACL-protected SQLite queue; it opens no public port.
The CPU worker's configured interpreter command is the private queue client.
`hosting/router_provider.py` sends bounded OpenAI-compatible requests through
operator-owned TLS endpoints or loopback tunnels. It captures actual response
usage and finish reason and rejects empty, truncated or mismatched completions.
The maintained Longleaf controller must supply fresh authenticated health and
full checkpoint/tokenizer/profile attestations. A model alias alone is insufficient.

Four GPUs scale interpretation throughput. They do not multiply the speed of one
answer or remove the CPU fitting/report queue. Multiple CPU workers also require
shared durable workspace storage or explicit ownership of each run by one worker.
Never put the router's SQLite files on NFS/SMB; remote workers need an authenticated
transport to a single queue owner. The local prototype is not that remote gateway.

## Telemetry tied to the login-owned run

`hosting/telemetry.py` writes an append-only, idempotent event ledger.
The broker's trusted run ID joins records to a login; student text never assigns
an owner. The analytics ledger contains no identity-to-email routing table.
Events preserve received lab messages, choices, checkpoints, artifacts, physical
inference attempts, model/revision/replica identity, queue time, elapsed response
time, outcomes and provider-reported usage. Nonstreaming latency is not TTFT.

The router measures Nemotron calls. It does not measure BlueChip's native GPT
tokens or capture every native chat turn. Tool-forwarded messages are labeled
`lab_api_received`, not a complete verbatim transcript. Status-only turns are
outside the present worker ledger. A supported platform event/export integration
is required before claiming complete original-turn coverage.

Token input includes system instructions and supplied evidence, not only the
student's typed question. Cache/reasoning fields are subsets when reported by
the current OpenAI-compatible provider. Missing counts remain unknown, never zero.
Duplicate callbacks do not add tokens; each real physical attempt counts once.
Later reconciliations supersede the same attempt in a new snapshot, not in a
previously delivered report. Opus debrief-generation usage is separate operator use.

## Codex orchestrates an individual debrief

`hosting/student_debrief.py` imports only one run's receipts, freezes the evidence,
computes metrics, and produces a minimal provider packet. Private run/session IDs
and delivery addresses are excluded. Known identifiers, paths, links and secrets
are redacted; the operator supplies roster/name terms and checks the export packet.
Pattern redaction does not guarantee anonymity for arbitrary free text.

Codex sends that packet and the versioned rubric to the metered Opus service at
high effort. For this user-requested interactive workflow, use Opus 5.5 explicitly;
an unattended caller follows the service-owned default policy and records the
actual model. A one-off example is uncached. Repeated cohort debriefs may cache
only the shared rubric for one hour, never an earlier student's evidence.

The response contains observations, Studio North next steps and AI-practice
recommendations with ready-to-use prompts. Each cites this snapshot's evidence.
Deterministic validation rejects foreign evidence IDs and invented quotations;
Codex also checks whether the cited evidence supports the prose. Prompt volume,
token counts and missing records do not justify grades, rankings or ability claims.
A rejected/unavailable narrative falls back to the measured activity report.

The rendered debrief is a separate personal artifact; it does not alter the
executive report's analysis. A separately protected delivery outbox holds the
authenticated recipient mapping. Sending claims a unique session/recipient key.
An uncertain send is held for reconciliation, never blindly resent.
The instructor's delivery-channel choice and real student recipient bindings
are still required. No student notifications are sent by the prototype.

## Reproduce and activate deliberately

1. Run `uv run --frozen python -m pytest tests/test_lab_telemetry.py tests/test_hosted.py`.
2. Import a completed run with `uv run --frozen python -m hosting.student_debrief
   --receipts <private-run-receipts> --run-id <run> --session-id <session>
   --output <private-debrief-folder>`. Add `--fixture` only for a rehearsal.
3. Inspect `evidence-packet.json`; send `opus-request.txt` through the authorized
   metered tool at high effort. Record the terminal response and actual usage.
   Validate, review and render it. Keep unknown provider outcomes pending; no
   hidden retries or fallback model. Do not mix another student's evidence.
4. For a new serving window, create a new frozen release and private config from
   `hosting/router-config.example.json`. Keep the prior release and its receipts.
   Configure `telemetry.session_id` and `telemetry.path` in the CPU worker, and
   set its `interpreter_command` to the lab Python plus `-m hosting.nemotron_router
   --config <private-config>`. Launch the daemon under the maintained supervisor.
5. Verify real student sign-in, isolated outputs, replica/tunnel health, expiry,
   queue recovery, usage reconciliation and private delivery before the class.
   Measure simultaneous fits/PDFs and inference, including p50/p95 queue latency.
   Four GPUs and an engine limit of eight sequences each are not a load test.

No visible terminal windows. Preserve the existing supervisor and process-tree
stop ownership; a future daemon launch needs its own representative launch QA.
This change creates no schedule and does not submit, extend or requeue GPU jobs.
The class opening should explain what is logged and how the personal debrief uses
it. Keep raw records in operator-controlled storage with a course retention policy.

## Source trail

- Current deployment and acceptance: `docs/bluechip-classroom.md`.
- Login/ownership enforcement: the separately versioned BlueChip broker and
  `hosting/bluechip-tool-schema.json`; the browser model cannot assign owner IDs.
- Workspace and checkpoint execution: `cohort_lab/hosted.py` and `cohort_lab/student.py`.
- CPU worker integration: `hosting/bluechip_worker.py`.
- Router, telemetry and debrief sources listed above; tests use synthetic identities.
- Serving design: [vLLM parallelism](https://docs.vllm.ai/en/latest/serving/parallelism_scaling/)
  and [MoE data-parallel deployment](https://docs.vllm.ai/en/latest/serving/data_parallel_deployment/).
