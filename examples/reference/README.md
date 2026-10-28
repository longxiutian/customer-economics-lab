# Reference outputs

These files are the observed outputs of the frozen release pipeline, not hand-
entered cohort examples. The report is an **instructor reference build**: it
shows the numerical evidence and leaves the learner's personal verdict open.
In a guided run, the saved learner verdict and recommended action are inserted
into that section before the report is compiled.

The editable report is `report/customer-economics-report.tex`; its figures and
style are included. The four interactive Archify HTML diagrams are in
`diagrams/`. The exact analytical and model tables are in `tables/`.

Machine-specific execution logs and generated SQL containing absolute local
source paths are intentionally not copied here. Run `lab.py` in a new output
folder to rebuild the complete analysis, including those logs and SQL adapted
to your local files. The reusable SQL view definitions are in the repository's
`sql/` folder; generated source-loading and export statements are saved on each
run. Do not use this inspection folder as a completed guided session.

The release reproducibility receipt is under `validation/`. It compares two
fresh processes on the tested platform, including the report PDF. Numerical
interpretations and model limitations are described in `docs/model-review.md`.
