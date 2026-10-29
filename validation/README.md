# Release validation — v3.0.0

The public release passed **164 tests**. Two independent CPU processes
computed source ETL, three NUTS fits, an Orduz-derived neural comparison and
observed-only future forecasts. After an additive experiment-exclusion comparison,
outcome-validator and visual/static-export repairs, ETL, challenge metadata,
diagrams and reports were independently replayed. Model source and all three
statistical input CSV hashes remained unchanged. **94
canonical artifacts match byte-for-byte**, including the tables, posterior draws,
future predictions, diagram exports, figures, TeX, PDF and audit metadata.
See `reproducibility.json` for precise scope and hashes, and `release.json` for
the executable source fingerprints. Page screenshots are visual QA evidence,
not additional scientific outputs.

Tests cover frozen observed inputs, censoring, acquisition timing, UCV coverage,
SQL reconciliation, experiments and nonbuyers, uncertainty, sampling diagnostics,
same-age/same-season financial comparisons, fixed-mix retention, all 24 cohort
trajectories, missing future cells, numbered exhibits, explicit stage gates,
saved judgments, read-only SQL, safe ZIP extraction and CPU operation even when
an inherited environment requests CUDA. Future-scoring tests use small public
fixtures, not the private evaluation outcomes.

The full-data model has maximum R-hat **1.0018**, minimum effective
sample size **1114**, and **0 divergences**. Historical
fits also pass the convergence gate. Sampling diagnostics do not establish that
the model's business assumptions are true.

Historical twelve-receipt contribution-value MAE is **$2.87** per
acquired customer versus **$23.43** for the simple baseline.
On the same 258 held-out retention observations, the main model's MAE
is **1.291**, the neural comparison's **1.180**,
and the simple baseline's **2.633**. The neural model
does not supply executive LTV. Historical validation is distinct from the
unreleased 2026 evaluation window, which was not used to choose these models.

The report contains 22 pages, 16
numbered figures and 18 numbered tables. It has one A3 schema
foldout, otherwise Letter pages, no overfull TeX boxes, and was visually checked.
The companion contains 12 slides and was checked
against the saved SQL output, including all 24 cohort rows and 96 paid-group
retention series. The maintained report style, local licensed Orduz source reading,
journey maps and knowledge-assets diagram are bundled.

Data generation belongs to a separate private instructor workflow. It has its
own 12 generation/holdout tests and repeated byte-identity check. Six boundary
checker tests exercise key/path/label leakage detection. Only the observed data,
blank future template, baseline forecasts and salted commitments are public.
The generation key, private skill, hidden parameters and future outcomes are
excluded from this release. Earlier tags retain their previously public generators;
an audit of 534 reachable objects and eight prior release assets found no current
private key or hidden answer data. History was preserved. Source reconstruction
is not part of the student analysis skill.

The public skill pauses after each stage. The separate guided-flow receipt covers
real stages 0–3 plus a logged query; the two instructor runs cover later numerical
and reporting work. These checks concern the documented Windows CPU environment;
they do not establish equal bytes on other platforms or accuracy for another
business. Earlier releases remain under their immutable tags.
