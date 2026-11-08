# Release numbering

Package metadata remains **1.7.0**; the current guided student edition is identified by its full source commit, not the older `v1.7.0` tag. The major number identifies the course-year edition: **1.x.x for 2026** and **2.x.x for 2027**. Within an edition, the minor number identifies a substantive milestone and the patch number identifies a revision to that milestone. Further revisions this year continue in the 1.x series; the year change does not authorize changes to the frozen data or model.

The 1.6.1 reindex changed release labels and download defaults. It preserved the report, numerical results, fitted models, source records and companion. The later 1.7.0 revision replaced legacy experiments with isolated acquisition-only pilots and refitted models after removing the old experiment-linked records; see [1.7 changes](v1.7-changes.md). The current bootstrap resolves `main` or an instructor-supplied ref once, saves the full commit SHA and archive hash, and requires the guided student files. It does not default to an archived tag.

## Historical mapping

| Reindexed label / tag | Original tag | Content |
|---|---|---|
| `v1.1.0` | `v1.0.0` | Initial staged customer-economics lab |
| `v1.2.0` | `v2.0.0` | Executive cohort-economics framework |
| `v1.3.0` | `v3.0.0` | Reproducible CPU workflow and private holdout boundary |
| `v1.4.0` | `v4.0.0` | Executive report and cohort segmentation |
| `v1.5.0` | `v5.0.0` | Journey diagnostics and cohort forecasting |
| `v1.6.0` | `v6.0.0` | Segmentation objective and incremental CAC |
| `v1.6.0+cover.1` | `v6.0.1` | Interim centered-title cover build |
| `v1.6.0+cover.2` | `v6.0.2` | Interim centered evidence/cutoff cover build |
| **`v1.6.1`** | `v6.1.0` | Skill contract and complete reproducibility checks, republished with the new numbering |

The first eight new tags are aliases for the exact original commits. The two cover-only builds use `+cover.1` and `+cover.2` to distinguish them within 1.6.0 without consuming the latest revision number, 1.6.1. The 1.6.1 publication includes the numbering changes and refreshed provenance; its analytical and presentation contents match the former 6.1.0 release.

Original tags, commits and validation receipts remain preserved. The eleven earlier GitHub releases contain the batch shortcut and lack the student-teacher skill; their release pages and attached downloads are retained as instructor-visible drafts, hidden from the public release list. Historical tags remain accessible for provenance, so this is removal from student distribution rather than a rewrite of Git history. Historical source archives retain their original internal version strings. Do not repoint old tags, relabel old receipts as new tests, or change data/schema versions merely to match a release label.

Some original tags overlap the new edition numbering. In particular, the old `v2.0.0` remains a preserved 2026 release, now mapped to `v1.2.0`; do not reuse it for 2027. Begin next year's edition with an unused 2.x tag, normally **2.1.0**. No 2027 release is created by this reindex.

## Publishing a revision

For a new tagged student release, update the project version in `pyproject.toml` and `uv.lock` and the README/setup instructions together. Record the decision in the root skill and keep historical mappings explicit. Verify that the exact tagged ZIP includes the student-teacher skill, enforces the nineteen checkpoints and exposes no batch shortcut. Keep the bootstrap's commit-pinning and archive checks. Follow [the reproducibility guide](reproducibility.md); instructor replay tools stay outside the student distribution. Mark only the verified guided release as **Latest**. Legacy noninteractive releases must remain hidden from student downloads.

The current frozen observed dataset is **5.1** (the 1.6.1 reindex retained 4.0), its schema remains separately versioned, and upstream article/style/software versions retain their original identities. Those are provenance identifiers, not the course-year release number.
