# Invisible report identifiers

The instructor selected a local, invisible footer instead of a global registry on November 9, 2026. Every new executive PDF produced by `cohort_lab.report.build_report` receives a random `SN-` identifier. The guided local workflow, temporary automatic trial and BlueChip backend all call this generator. A hosted deployment must explicitly adopt the revised release; already frozen services and previously downloaded repositories do not update themselves.

The identifier is saved once as `report_identity.json` in the output workspace, repeated in each PDF page's footer text layer, and recorded in PDF metadata and the report manifest. PDF text rendering mode 3 makes it invisible on white, colored and printed pages. It is not white text. It contains no name, email, account, device identifier or timestamp. No network call, login or external registration is made.

Rebuilds in the same workspace retain the ID, including after report-stage invalidation. Separate output workspaces receive separate IDs. Copying the PDF preserves its ID; copying an entire completed workspace preserves it too. Do not copy the identity file from a reference or another student's workspace when starting a new run. Existing reference PDFs are previews, not completed student runs.

## Read and count

After receiving PDFs, the instructor or their AI can extract and group the IDs without inspecting identical report prose:

```text
uv run --frozen python scripts/report_ids.py path/to/reports-folder
```

The command reads PDFs directly inside that folder, reports distinct run IDs and repeated IDs, and lists unmarked or inconsistent PDFs separately. File arguments are also accepted. Run it separately for each class session's folder. There is no automatic central tally. A renamed or copied file counts once because its embedded ID is unchanged.

The count measures distinct report runs, not unique authenticated students. A student can start another workspace or edit a PDF; the footer is not a signature or proof of independent work. Re-saving through software that strips the text layer can remove it. Names or opaque IDs typed by a learner are not accepted as identity proof.

## Reproduction and verification

The statistical inputs and seed do not derive the ID: otherwise every student using the same data would receive the same identifier. The random ID is a saved run input. Preserve it for an exact same-run rebuild. The report manifest binds the saved identity and final stamped PDF; validation requires a matching invisible footer on every page, including the landscape schema page, and matching PDF metadata.

Strict byte comparison remains the default. To compare different completed runs while excluding only this intended identifier difference, use `scripts/verify_reproducibility.py --ignore-report-identity` with the usual run and receipt arguments. Each run is fully validated first. The comparison removes only the controlled marker stream, its font resource and its metadata, and normalizes the corresponding manifest fields. Other PDF content, metadata and analytical artifacts still participate in comparison. This is content equality after that explicit normalization, not byte equality of the original files.

The cover validator rejects MBA, MSM, MQM or KFM course numbers and requires the common three-line credit: Kenan-Flagler Business School; Managing Customer Data; Mod II 2026. Both report compilation and final artifact validation apply this check.
