# BlueChip service reliability

This is an operator contract. Students keep their existing BlueChip conversation
and use **check progress** during an interruption. They do not repair the backend.

## Separate observation failure from allocation failure

A missing, timed-out, malformed or stale SSH observation means **unknown**. It
does not prove that a CPU/GPU allocation ended. Keep previously owned tunnels
alive through a temporary observation failure, up to their original deadline.
Pause new model-dependent admissions when authenticated model health expires.
Resume only after a fresh observation validates the same allocation, host,
runtime, model and deadline. Verified terminal Slurm state, changed ownership,
authentication failure or model identity mismatch follows its explicit failure
path; it must not be recast as ready using a cached observation.

Use bounded read-only status probes and trusted frontend fallback. Status probes
must not depend on importing the large model environment on a login server.
Reconnect only transport for the same authorized allocation. Preserve strict
host-key verification and previously completed smoke/tokenization receipts.
Never replay a model request because its SSH connection or acknowledgment failed.

## Independent bridge and debrief lifetimes

`hosting/session_supervisor.py` is the reusable session owner. It starts one
bridge component and one debrief component. Each component has an independent
process tree; an early exit in either is recorded while its healthy sibling
continues. The supervisor does not restart workers or replay fits/reviews.
The bridge component owns bounded connection recovery internally.

No visible terminal windows. On Windows, both the outer owner and each component
use the maintained `pythonw.exe` / `hidden_launcher.py` Windows Job Object chain.
Each console child uses `CREATE_NO_WINDOW`. Cancellation closes all owned trees.
The supervisor enforces the original absolute expiry and a monotonic time limit,
so moving the system clock backwards cannot extend the session.

The private operator JSON supplies:

| Field | Meaning |
| --- | --- |
| `session_id` | One explicit session identity shared by both components |
| `expires_at` | Original authorized Unix expiry, shared by both components |
| `state_dir` | Absolute private folder for the exclusive launch intent and receipts |
| `frozen_files` | Absolute script/config paths mapped to verified SHA-256 hashes |
| `windows_launcher` | Absolute `pythonw.exe` and maintained `hidden_launcher.py` paths |
| `components` | Exactly `bridge` and `debrief`, each with `command` argument array, absolute `cwd`, `session_id` and `expires_at` |

Bind all imported operator helpers and private worker configurations before
launch. Keep the configuration outside Git; provide credentials through the
existing protected environment. The bridge does not inherit the debrief service
bearer, and the debrief component does not inherit GPU tokens. No secrets belong
in command-line arguments. The bridge controller separately verifies its frozen
deployment adoption record and original allocation receipt.

Launch `python -m hosting.session_supervisor --config <private-operator-config>`
under that maintained outer launcher. This replaces the old launcher that exited
as soon as the SSH child exited. Do not wrap the old combined launcher as a child,
because it would still own and terminate unrelated review processes.

`launch-intent.json` prevents duplicate ownership. `status.json` distinguishes
process liveness from actual broker readiness. `operator-attention.json` records
an early component failure and the required reconciliation; it is a local
operator record, not an email or an automatic repair claim. `exit.json` records
cleanup. A failed status-file write cannot terminate healthy components. Preserve
all receipts when repairing a component; do not delete the intent to force a
second full session start.

## Preserve jobs and delivery during interruptions

The broker accepts each operation under its original request ID and expected
revision. A worker can claim new interactive/analysis work only when that worker
has a fresh heartbeat, ready CPU state and fresh model evidence. Missing, stale,
malformed or implausibly future-dated evidence pauses admission; it does not
remove accepted jobs or change their queue rank. Completed-evidence debriefs
are independent of the Nemotron connection.

Queued students see their saved request, current position and timestamp.
Running work is not resubmitted. If a worker lease expires, reconcile its
durable spool; do not hand uncertain execution to a replacement worker.
Result redelivery may retry idempotently after a lost acknowledgment, without
rerunning the computation or review. Completed report and debrief downloads
remain available through their original expiry while compute services recover.

The BlueChip prompt uses the returned service notice, shows saved progress and
available downloads, and keeps the same workspace. It does not diagnose a dead
GPU from a heartbeat timeout or tell students to reinstall software.

## Verification and promotion

Run these tests from the lab checkout:

```text
python -m pytest tests/test_session_supervisor.py tests/test_worker_delivery.py -q
```

On the target Windows host, set `STUDIO_NORTH_TEST_HIDDEN_LAUNCHER` to the maintained
launcher and run `tests/test_session_supervisor_windows.py`. Those opt-in tests
start only local fixture processes. They observe visible windows, exercise an
early successful/failed bridge exit, verify that review work survives, and verify
deadline/cancellation cleanup of grandchildren. They make no network, provider,
email or scheduler calls.

In the separate broker checkout, run `scripts/test-service-recovery.mjs` alongside
the existing broker, automatic, classroom-burst, session-debrief, retired-worker
and completion-snapshot suites. The recovery fixture queues 45 synthetic learner
requests, removes fresh model health, verifies stable queue order and existing
downloads, allows independent debrief work, restores health and confirms that
the same queued request resumes. It also checks uncertain execution and expiry.

Before class deployment, pin the supervisor, bridge helpers, analytical release,
broker build and agent instructions separately. Validate the exact deployment
adapter without opening a second live tunnel. Then rehearse an authorized fresh
student workflow through the actual BlueChip agent, including both PDF downloads
and private workspace isolation. Record the real GPU/CPU allocation and measured
capacity. Offline 45-request admission tests establish queue behavior, not
45-user inference throughput or a class-day reservation.

The November 11 running session retains its frozen analysis and existing recovery
processes. Staged changes do not silently replace that session. The immediate
observation-failure fix and the broader next-session candidate have separate
verification receipts.
