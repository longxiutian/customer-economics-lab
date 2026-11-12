# FAQ 1: actual files in the browser lab

The BlueChip `files` action reads the signed-in learner's saved workspace and a
worker-observed file manifest. It does not create a workspace, call a model,
expire jobs, run SQL, refit a model or advance a checkpoint. It accepts no run ID,
email, root or path from the learner. The broker uses the existing platform
identity boundary to select the owner.

The returned `answer_markdown` supplies the compact tree, full source and output
locations, file purposes, DuckDB explanation, a retention-table-to-figure trace,
and working output downloads. BlueChip relays it without inventing paths.
`file_map.files` retains the full allowlisted inventory, byte sizes and hashes.
Observations have timestamps and indicate whether the saved revision has changed.
Missing or future artifacts are not presented as files that already exist.

DuckDB runs in memory. The frozen source and saved analysis manifest establish
its implementation and version. Saved CSV inputs, executed SQL, sorted output
tables and manifests reproduce the calculation; no analytical database file is
required. The retention triangle uses people, transactions, subscription periods
and acquisition attribution. SQL aggregates cohort-age rows; Python pivots and
renders them. Channel holdouts are used separately for acquisition incrementality.

Remote paths are not mounted on a student's laptop. Downloaded filenames can be
opened in the browser's chosen download folder; the service cannot inspect or
invent that local path. The separate debrief service supplies downloadable copies;
the file map does not assert that those copies are on Longleaf.

## Worker and operator contract

`hosting/file_manifest.py` is standard-library-only. It reads approved files,
checks source hashes against the saved release fingerprint, refuses symlink
escapes, and performs a bounded database-file scan. It does not import or invoke
the lesson. `hosting/file-catalog.json` mirrors the reviewed broker catalog;
register each new frozen release in the broker before classroom deployment, after
reviewing that release's code against the stated DuckDB and lineage facts. Generate
the worker catalog using the broker's `scripts/export-file-catalog.mjs`; its
`--check` option verifies parity. The release registry stays outside the hashed
analytical source, avoiding a self-referential release hash.
Set `file_map_paths_disclosable: true` in the reviewed operator CPU-pool config.
New CPU workers then publish a separate observation after successful result delivery.
Metadata failure is reported as `file_map_pending` and cannot invalidate a fit.
Debrief workers do not replace the analysis file map.

Historical releases must remain immutable. Copy this observer and its catalog
outside the frozen source tree and run its CLI with the existing private config,
explicit source/runtime, and `--attest-paths-disclosable`. Inspect `--dry-run`
first. Backfill refuses a run with active work; it changes only `run_manifests`,
not checkpoints, reports, receipts, packets or release files. No worker heartbeat,
GPU allocation or statistical job is required. Never commit the private config
or a student's actual manifest to the public repository.

Downloads remain scoped to artifacts in the owner's current packet. They are
checked against stored metadata and object availability. Hosted-file associations
also require matching file hashes. The broker issues personal 30-minute bearer
links only after authentication; changing a run, artifact or expiry invalidates
the signature. `LAB_ARTIFACT_ACCESS_UNTIL` sets a separate finite retrieval period
(30 days after compute expiry for the November pilot, with a 90-day code ceiling).
Expired retention produces no dead download links. This setting never extends
compute access or enables the retired automatic route. Preserve the session ID
through retrieval; rotating it changes the existing owner lookup.

Acceptance requires API isolation and read-only tests, an authenticated BlueChip
FAQ response for its actual run, and successful report/debrief downloads with
matching hashes. A fixture API test is not proof of another student's sign-in.
