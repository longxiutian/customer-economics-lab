# Release numbering

The current release is **1.6.1**. The major number identifies the course-year edition: **1.x.x for 2026** and **2.x.x for 2027**. Within an edition, the minor number identifies a substantive milestone and the patch number identifies a revision to that milestone. Further revisions this year continue in the 1.x series; the year change does not authorize changes to the frozen data or model.

This reindex changes release labels and download defaults. It preserves the report, numerical results, fitted models, source records and companion. Current package metadata, the lock file's project entry, setup instructions and bootstrap default all use 1.6.1. Build manifests are regenerated against the updated instructions and metadata.

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

The first eight new tags are aliases for the exact original commits. The two cover-only builds use `+cover.1` and `+cover.2` to distinguish them within 1.6.0 without consuming the latest revision number, 1.6.1. The current 1.6.1 publication includes the numbering changes and refreshed provenance; its analytical and presentation contents match the former 6.1.0 release.

Original tags, release URLs, attached files and validation receipts remain available. Existing GitHub release titles display the new labels with their original tags identified; their original notes remain below a mapping notice. Historical source archives retain their original internal version strings. Do not rewrite old commits, repoint old tags, relabel old receipts as new tests, or change data/schema versions merely to match a release label.

Some original tags overlap the new edition numbering. In particular, the old `v2.0.0` remains a preserved 2026 release, now mapped to `v1.2.0`; do not reuse it for 2027. Begin next year's edition with an unused 2.x tag, normally **2.1.0**. No 2027 release is created by this reindex.

## Publishing a revision

Update the project version in `pyproject.toml` and `uv.lock`, the bootstrap default, the README/setup download instructions, and the matching archive-URL assertion together. Record the decision in the root skill and keep historical mappings explicit. Refresh report provenance through the public replay procedure in [the reproducibility guide](reproducibility.md), then verify the exact tagged ZIP. Mark the intended GitHub release as **Latest** explicitly: the preserved legacy 6.x tags must not displace the current 1.x release merely because their numbers are larger.

The frozen observed dataset remains **4.0**, its schema remains separately versioned, and upstream article/style/software versions retain their original identities. Those are provenance identifiers, not the course-year release number.
