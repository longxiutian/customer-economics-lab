# Studio North team forecast

Replace this heading with your team and model name. Explain the retention and revenue assumptions, what varies across customers or cohorts, your historical training/validation cutoffs, and why the model should extrapolate beyond observed ages. Record the final configuration before requesting private-holdout evaluation.

`main.py` exposes `predict(tables, prediction_grid, *, seed)` and a standard command. Its supplied model is a simple pooled constant-hazard example. It is **not** the official hierarchical shifted-Beta-Geometric + Gamma reference. Replace the prediction function with your own method; retain the interface and validation.

```text
uv sync --frozen
uv run --frozen python main.py --data-dir /path/to/released/data --prediction-grid prediction_grid.csv --output outputs/predictions.csv --seed 20261116
```

The eight observed input tables stop on December 31, 2025. Private future outcomes are never model inputs. Each dictionary key is a CSV filename without `.csv`; dates are ISO strings, numeric fields are numeric, and empty nullable fields are missing. The supplied grid contains only keys and observed exposures. Preserve every row and add expected retained members, net revenue and contribution in dollars. Contribution is before acquisition cost.

Keep `pyproject.toml` and `uv.lock` together. Add dependencies with `uv add`, then verify a clean `uv sync --frozen`. The evaluation environment uses Python 3.12, four CPU cores, 16 GiB memory, no GPU or runtime network, and a 60-minute prediction limit. Fit from the supplied observed tables within that budget; do not require locally cached artifacts or external services. Use the seed for stochastic operations. Dependencies may be installed during environment preparation.

Keep code, model explanation and historical validation in the public team GitHub repository. Do not publish credentials, personal chat transcripts or private outcomes. Submit its URL and full commit SHA; the instructor evaluates that exact commit. The authoritative schema, score and limits are in `submission-contract.json`.

The primary score is contribution WAPE after aggregating channel/need cells into each acquisition-cohort × future-calendar-month point. Lower is better. The best team receives one bonus point; ties and submission timing are handled by the instructor. Format checks are not hidden-outcome scores.
