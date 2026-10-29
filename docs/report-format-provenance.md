# Executive report formatting provenance

The v2 report uses Longxiu Tian's maintained **build-longxiu-research-briefs** visual system, not a newly approximated report theme. The author requested that the system be included in this public workflow so another team can reproduce it without access to a private skill installation.

`templates/longxiu-research-brief.sty` is the unmodified, source-free visual package, version `2026-08-22-v1.1`. Its SHA-256 is pinned in `templates/report-style-manifest.json`. The file defines US Letter portrait geometry, Source Sans typography, the forest-green/ochre palette, page furniture and restrained callouts. It contains no private paper content or empirical claims.

`templates/labreport.sty` is the report-specific wrapper. It changes running labels and semantic components for a customer-economics management report while importing the maintained visual package. `templates/customer-economics-report.tex.j2` is the original report structure. The supporting skill and its style reference under `skills/executive-report/` carry the relevant report-writing, appendix, evidence and visual-verification rules. The original system's paper-portfolio and radar-chart conventions do not apply to this business report.

Generated reports copy both style files beside editable TeX. Their manifest records the upstream package version/hash and the wrapper/template hashes, as well as numerical input and figure hashes. A downloaded ZIP is sufficient; the report does not access a personal skill directory or require Git.

The complete relational schema uses one A3 landscape foldout appendix. This is an explicit, report-specific readability exception in the wrapper; all executive and other appendix pages use the maintained US Letter portrait layout. It does not modify the vendored visual package.

The report's body is managerial prose. Stage-by-stage student prompts remain in the main `SKILL.md`; they are not printed as classroom instructions or blank judgment fields in the report. Methods, actual parameter estimates, prediction checks and dataset-level UCV documentation belong in technical appendices. That separation is a durable requirement of the bundled supporting skill.
