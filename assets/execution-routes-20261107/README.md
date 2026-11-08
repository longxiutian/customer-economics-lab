# Studio North: three execution routes

Nine-slide integration module for the main Studio North lab deck, revised November 7, 2026. It replaces the earlier separate BlueChip architecture supplement. It is not a second course deck.

## Integration into the day slides

The MBA 743 / KFM 740 chat owns the latest instructor-edited main deck. As confirmed by that chat, the main source has **23 slides and nine FAQs**; preserve those current FAQs and their order. Insert the separately authored customer-up business motivation after the conceptual roadmap. Replace the obsolete ChatGPT classroom-access slide (old slide 13) with this module, immediately before the existing FAQ divider. Renumber the complete deck and reconcile old browser-only notes.

| Module slide | Purpose | Actual diagram |
| --- | --- | --- |
| 1 | Navy subtopic divider | — |
| 2 | Three routes, one learning workflow | — |
| 3 | Personal Codex / Claude Code / VS Code agent | `personal.png` |
| 4 | UNC-funded MCP scenario, explicitly TBD | `university-mcp.png` |
| 5 | BlueChip, CPU analysis and Longleaf interpretation | `bluechip.png` |
| 6 | Four independent GPU replicas and a router | `four-gpus.png` |
| 7 | Login-owned persistent workspaces | `workspaces.png` |
| 8 | Measured, estimated and unknown usage | — |
| 9 | Common personal debrief and business report | `debrief.png` |

All six diagrams are genuine **Archify 3.2.0 `editorial` renders**, matching the main report's `knowledge-assets` diagram. Use the supplied high-resolution PNGs or native SVGs. Do not reconstruct them as plain PowerPoint boxes. Titles, captions and other slide text remain editable. The JSON/HTML/SVG files are the editable diagram masters.

The saved preview is Page `page_4e018199c74c8191a445023b5b536679`, state 12. Reconnect that Page to obtain a current Artifact Session reference. `slides.mjs` contains the exact native text/layout and complete speaker notes. To reproduce a fresh staging deck, run `start`, `personal`, `hosted`, `finish` as separate Artifact Session callbacks. **Never call `start` on the main course deck: it clears the staging presentation.**

For non-destructive integration into an Artifact Session main deck, use `appendSection`. It appends nine slides and returns their IDs; reorder those IDs before the existing FAQ divider, then renumber. Other authoring backends should reproduce the native text/positions from `slides.mjs` while embedding the exact supplied diagrams. The `renders/` images document the inspected composition; do not flatten whole slides into images.

## Reproduce the diagrams

From a checkout containing pinned commit `ff9c9d727ce298d16b91ba698aa99a0b6b1d2c51`, install the locked Python environment and `npm ci --prefix tools` plus the pinned Playwright Chromium. Run:

```text
python build_diagrams.py --repo PATH_TO_LAB_REPO --node PATH_TO_NODE --render
```

The candidates cite committed source ranges at that revision. Archify `finalize --quality showcase` checks schema, repository sources, delivery, static quality and browser output. All six passed. `export_slide_diagrams.mjs` derives from the report's native SVG exporter; it preserves the editorial colors, icons and routing while setting node text to 16/14 px for presentation use. It exports a native SVG and a 2× PNG, without screenshotting reader controls. Existing receipts are reused only when the specification hash matches.

## Shared learning debrief

The root and student-teacher skills now require the same personal learning debrief for all three routes. The portable implementation, documentation and tests are in the pinned commit. The final checkpoint creates an evidence scaffold, which the current authorized agent must review and personalize. Instructor-orchestrated Opus 5.5 high can refine the same packet when available; a separate student Opus subscription is not required.

Real provider/harness counters are recorded when exposed. Otherwise the helper labels an estimate of recorded text only and leaves total inference usage unknown. Native-client, university gateway and Nemotron streams remain separate. Local records are not automatically uploaded to the instructor. The hosted broker remains responsible for authenticated identity and private delivery.

## Status and verification

- 38 focused portable-debrief, telemetry, hosted-workflow and guided-lesson tests passed. The final-checkpoint test confirms that the report and debrief are produced together without changing the explicit `next step` gates.
- Every slide was rendered and individually inspected. Slide 5 was re-rendered after adding visible classroom-activation status. No clipping or overlaps were observed. The report-style reference was compared with the actual exported diagrams.
- The root and student-teacher skills were published on GitHub main and independently retrieved with HTTP 200. The local academic-slide skill and its backend/QA references now require genuine Archify renders by default.
- The one-GPU rehearsal is historical evidence. Its window expired; the four-GPU classroom service, UNC-funded MCP scenario and private class-wide debrief delivery are not claimed active.
- Opus 5.5 max review did **not** complete: two text consultations exhausted output allowances (7,000 and 24,000 output tokens); a media-tool call returned an execution error without a usable receipt. These are not approvals. The rendered review reported here is Codex's direct inspection. Details are in `reviews/qa.json`.

## Business story and Day page handoff

The MBA course chat is adding the business subsection: operations, finance and growth decisions can be evaluated from the customer up. It uses Longxiu's recollection of two MBA alumni, without invented names or a fabricated quotation. The fictional narrative is grounded in `docs/business_brief.md`; customer contribution value supports decisions but is not a complete enterprise valuation.

The same chat confirmed updates to the November 16 MBA and November 17 KFM Day pages: UNC BlueChip sign-in, instructor-supplied classroom agent link pending, start button or short prompt, and standalone `next step`. It does not advertise the expired debugging link as live.
