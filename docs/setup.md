# Setup before class

The public source ZIP is sufficient. Git, a GitHub account, and a SQL database server are not prerequisites. The script `scripts/bootstrap.py` downloads the v1.0.0 source archive over HTTPS into a new empty folder using Python's standard library.

## Python environment

Use Python **3.12** and [uv](https://docs.astral.sh/uv/). Ask your local AI agent to locate an existing compatible interpreter first. From the extracted lab folder:

```text
uv sync --frozen
```

If the machine has several interpreters, select a verified Python 3.12 explicitly:

```text
uv sync --frozen --python /path/to/python3.12
```

The exact resolved package versions are in `uv.lock`. The core model uses CPU JAX/NumPyro; a GPU is not required. Keep the environment inside the repository's `.venv`, rather than changing unrelated global packages. Network access is needed for the initial package download.

## Diagram and report tools

- **Node 18 or newer** runs the bundled Archify package. Check `node --version`. Archify's required source and license are included; no Git-backed skill installer or runtime service account is needed.
- **Tectonic or pdfLaTeX** compiles the report. The renderer checks `COHORT_TEX_ENGINE` if set, then `tectonic` and `pdflatex` on PATH. On Windows it can also use an existing WSL pdfLaTeX installation. The report needs Source Sans (`sourcesans.sty`) plus the standard graphics, table, and TikZ packages in its template. Complete the first compilation before class so any package downloads are cached.
- An environment-specific renderer path may be supplied through `COHORT_TEX_ENGINE`. The lab does not require shell escape. A failed PDF build preserves the editable `.tex` and figures and reports the failure.

## Readiness

```text
uv run --frozen python lab.py start
```

Stage 0 verifies the data manifest, Python packages, Node, and renderer availability. It stops at setup if a required component is missing. Fix that component within the same stage and say `next` to retry setup; this does not skip to the source analysis.

For a source-only environment, `uv run --frozen python lab.py --no-pdf start` explicitly omits PDF compilation. The final output must then be described as editable TeX, not a successfully rendered PDF.

The full instructor smoke run should be completed on each supported classroom platform before teaching. Package detection alone does not establish that model fitting, fonts, and PDF compilation all work. Never describe a platform as tested merely because its dependencies are theoretically available.

## Starting again or using a separate group folder

Use a new output directory; preserve existing student work:

```text
uv run --frozen python lab.py --output outputs/my-group start
```

Keep the same output option on subsequent commands. A resumed chat reads the saved state, choices, and input fingerprints. If frozen inputs were edited, restore the public release and use a new output folder; do not rewrite the manifest to make altered records pass.
