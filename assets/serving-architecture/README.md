# Studio North: serving architecture and personal debriefs

This teaching supplement explains BlueChip sign-in, the CPU analysis worker,
Longleaf/Nemotron, a fair router across four independent GPU servers, isolated
student workspaces, and Codex-orchestrated personal feedback using Opus 5.5 (high).

The 11-slide editable presentation is saved in Spaces as page
`page_4e018199c74c8191a445023b5b536679`, artifact
`artifact_external_ca7b8f3a-bb9e-43ea-926e-de231205af62`, state version 7.
Open it through the delivery message or reconnect that page with Artifact Session.
PowerPoint export is available from the presentation viewer.

Open `index.html` for the four interactive Archify diagrams and the example
debrief. The example uses instructor acceptance-test records, not student data.
It includes 25 lab requests, one fresh statistical fit and 20 Nemotron completions
with 127,200 reported tokens. The Opus debrief itself used 6,598 separate tokens.

## What is implemented

Source snapshot `3a109560dc064217bb662f4109e8265f7307497a` adds fair routing,
idempotent prompt/usage records, frozen evidence by student run, validated feedback,
and a separate delivery outbox. Seventeen router/telemetry and hosted-lab tests passed.
The source change is a local commit; it has not been pushed or deployed.

The one-GPU instructor rehearsal generated the full report from fresh fits.
Four live GPU replicas, classroom CPU concurrency, real student sign-in validation,
and the selected personal delivery channel remain deployment work. The frozen
rehearsal release, public broker and BlueChip agent were not changed here.

The ledger measures requests received by the lab API and Nemotron's reported
tokens. It does not provide a full original BlueChip transcript or native BlueChip
model usage. Missing usage remains unknown. Token volume is not a learning score.

## Reproduce the materials

Use the `customer-economics-lab` checkout containing the source snapshot above.
The standalone archive includes `source-change.patch` against base
`aa32de4a33bd4c026ce38b30677ddb2b0ba8ca71`; a fresh checkout at that base can apply
the patch if the local source commit has not been published. Do not apply it twice.
Alternatively, `source-snapshot.bundle` preserves the actual commit and its new
objects, with that base commit as a prerequisite. From a checkout containing the
base, run `git fetch /path/to/source-snapshot.bundle 3a109560dc064217bb662f4109e8265f7307497a`
to make the pinned source object available even before publication. The bundle
does not contain the rest of the repository's history.
The scripts locate a surrounding lab checkout or use `STUDIO_NORTH_REPO`.

1. **Diagrams:** run `python build_diagrams.py`, then
   `python finalize_diagrams.py overview four-gpus workspaces debrief`.
   Node must be on PATH. The lab's vendored Archify 3.2.0 performs validate,
   deliver, check and browser-check. Source evidence is pinned to the architecture
   contract at the recorded commit. Regeneration requires that Git object;
   the supplied finalized HTML/JSON remains inspectable without regeneration.
2. **Slides:** in a new empty, viewer-bound Artifact Session, import `slides.mjs`
   and run its callbacks sequentially: `cover`, `opening`, `systems`, `feedback`.
   Pass each callback to `artifactSession.run` with the newly bound artifact ref.
   Do not run the creation callbacks against the completed presentation.
   The relative `assets/` and `diagrams/` directories must stay beside the module.
   All diagram shapes and labels in the deck are editable native elements.
3. **Example debrief:** run `python finish_debrief.py` to validate the recorded
   Opus response and render HTML. This reuses the saved provider response; it
   does not call a model or incur new inference. `reviews/adjudication.md` records
   the Codex correction. Then run `python render_debrief_pdf.py` with ReportLab
   4.4.9 and Arial regular/bold fonts. The default font folder is Windows Fonts;
   on another OS set `STUDIO_NORTH_FONT_DIR` to a licensed Arial font directory.
   ReportLab's invariant mode removes changing PDF timestamps/IDs. Render both
   pages with Poppler and inspect them after any content or layout change.
4. **A new student debrief:** follow `docs/serving-architecture.md` in the lab
   repository. Freeze only that student's records, inspect the redacted packet,
   obtain one authorized Opus response, validate citations and exact quotes,
   review the reasoning, and deliver through the authenticated recipient mapping.
   Regenerating a model response may change its wording; the saved response and
   evidence hashes reproduce the reviewed example exactly.

The original private event database, identity mapping and private snapshot are
excluded from this package. `debrief-example/evidence-packet.json` is the redacted
instructor fixture used by Opus. Never replace it with a whole-class transcript.

## Provenance and checks

`manifest.json` records source revisions, versions, status and file hashes.
The scoped `.gitattributes` preserves exact generated artifact, evidence, receipt
and request bytes instead of normalizing their line endings during Git checkout.
`reviews/qa.json` records visual and functional checks. All four Archify diagrams
passed their automated browser gates. Every final slide and both PDF pages were
reviewed visually; the four-GPU Archify canvas was also inspected. Other Archify
canvases have automated checks, not a claimed manual review.

Course cover assets are reused from the current instructor course deck. Their
hashes are recorded with the source package. The style follows the course's Arial
type, Carolina/navy palette, opening color key and teaching-role labels.

Implementation evidence is in the pinned architecture contract. Primary serving
references are [vLLM parallelism and scaling](https://docs.vllm.ai/en/latest/serving/parallelism_scaling/)
and [vLLM data-parallel deployment](https://docs.vllm.ai/en/latest/serving/data_parallel_deployment/).
Our design uses independent complete replicas; it does not assume the synchronized
MoE data-parallel configuration is interchangeable. These are design references,
not evidence of a completed four-GPU classroom load test.

One unrelated preexisting edit, `docs/companion-slides.md`, was present in the lab
checkout. It was not modified, staged or included in the source patch.
