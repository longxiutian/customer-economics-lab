"""Orduz-derived Bayesian neural retention benchmark, separate from decision LTV.

This is a real two-layer Bayesian network, implemented directly in NumPyro/JAX
rather than through Flax. The network architecture and Laplace priors follow
Orduz; the conditional churn likelihood is an explicit contractual-renewal
adaptation. The model never sees simulation parameters or latent customer truth.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

os.environ["JAX_PLATFORMS"] = "cpu"
os.environ["JAX_ENABLE_X64"] = "true"
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd

KEYS = ["cohort_month", "channel", "primary_need"]
TRAINING_CUTOFF = "2025-10-01"
SCORING_END = "2026-01-01"
HIDDEN_UNITS = 4
POSTERIOR_DRAWS = 400
MIN_STEPS = 10000
FEATURE_NAMES = ["age_month/23", "(cohort_index-11.5)/11.5", "need_build_skill",
                 "channel_partner", "channel_organic"] + [f"calendar_month_{m:02d}" for m in range(2,13)]


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def _frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False, float_format="%.10f", lineterminator="\n").encode("utf-8")).hexdigest()


def _features(frame: pd.DataFrame) -> np.ndarray:
    """Fixed transforms require no fitted scaler and no held-out data statistics."""
    month = pd.to_datetime(frame.calendar_month).dt.month.to_numpy()
    return np.column_stack([
        frame.age_month.to_numpy(dtype=float)/23,
        (frame.cohort_index.to_numpy(dtype=float)-11.5)/11.5,
        (frame.primary_need == "build_skill").to_numpy(dtype=float),
        (frame.channel == "partner").to_numpy(dtype=float),
        (frame.channel == "organic").to_numpy(dtype=float),
        *[(month == m).astype(float) for m in range(2,13)],
    ])


def _validate_panel(frame: pd.DataFrame) -> pd.DataFrame:
    required = KEYS+["cohort_index", "age_month", "calendar_month", "n_retained"]
    if set(required)-set(frame):
        raise ValueError(f"Benchmark is missing columns: {sorted(set(required)-set(frame))}")
    f = frame[required].sort_values(KEYS+["age_month"]).reset_index(drop=True).copy()
    f["cohort_month"] = pd.to_datetime(f.cohort_month).dt.strftime("%Y-%m-%d")
    f["calendar_month"] = pd.to_datetime(f.calendar_month).dt.strftime("%Y-%m-%d")
    if f.duplicated(KEYS+["age_month"]).any():
        raise ValueError("Duplicate benchmark cohort-age cells")
    if not np.isfinite(f[["cohort_index", "age_month", "n_retained"]].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite benchmark input")
    if ((f.n_retained < 0) | (f.n_retained != np.floor(f.n_retained))).any():
        raise ValueError("Retained counts must be nonnegative integers")
    if not set(f.channel).issubset({"search", "partner", "organic"}) or not set(f.primary_need).issubset({"save_time", "build_skill"}):
        raise ValueError("Unsupported benchmark channel or need")
    for _, g in f.groupby(KEYS, sort=True):
        if not np.array_equal(g.age_month, np.arange(len(g))):
            raise ValueError("Benchmark ages must be consecutive from zero")
        if (np.diff(g.n_retained) > 0).any():
            raise ValueError("Benchmark requires absorbing contractual churn")
        expected = pd.date_range(g.cohort_month.iloc[0], periods=len(g), freq="MS").strftime("%Y-%m-%d")
        if not np.array_equal(g.calendar_month, expected):
            raise ValueError("Benchmark calendar and acquisition ages disagree")
    return f


def _risk_set(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.sort_values(KEYS+["age_month"]).copy()
    f["previous_retained"] = f.groupby(KEYS, sort=True).n_retained.shift(1)
    f = f[(f.age_month > 0) & (f.previous_retained > 0)].copy()
    f["n_churned"] = f.previous_retained-f.n_retained
    if ((f.n_churned < 0) | (f.n_churned > f.previous_retained)).any():
        raise ValueError("Invalid monthly churn risk set")
    return f


def network_hazards(features: np.ndarray, draws: dict) -> np.ndarray:
    """Evaluate all posterior networks: draws × observations, without RNG."""
    from scipy.special import expit
    x = np.asarray(features, dtype=float)
    hidden = expit(np.einsum("nf,dfh->dnh", x, np.asarray(draws["hidden_weights"]))
                   + np.asarray(draws["hidden_bias"])[:, None, :])
    logits = np.einsum("dnh,dh->dn", hidden, np.asarray(draws["output_weights"]))
    return expit(logits+np.asarray(draws["output_bias"])[:, None])


def _fit_posterior(train: pd.DataFrame, seed: int, steps: int) -> tuple[dict, dict]:
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import SVI, Trace_ELBO
    from numpyro.infer.autoguide import AutoNormal
    from numpyro.infer.initialization import init_to_value
    from numpyro.optim import ClippedAdam
    from scipy.special import logit

    numpyro.enable_x64()
    if jax.default_backend() != "cpu" or not jax.config.x64_enabled:
        raise RuntimeError("The benchmark release requires CPU JAX with float64")
    risk = _risk_set(train)
    if len(risk) < 12:
        raise ValueError("Insufficient observed monthly renewal risk sets")
    x = jnp.asarray(_features(risk))
    at_risk = jnp.asarray(risk.previous_retained.to_numpy(dtype=float))
    churned = jnp.asarray(risk.n_churned.to_numpy(dtype=float))
    n_features = len(FEATURE_NAMES)

    def specification():
        w = numpyro.sample("hidden_weights", dist.Laplace(0., 1.).expand((n_features, HIDDEN_UNITS)).to_event(2))
        b = numpyro.sample("hidden_bias", dist.Laplace(0., 1.).expand((HIDDEN_UNITS,)).to_event(1))
        v = numpyro.sample("output_weights", dist.Laplace(0., 1.).expand((HIDDEN_UNITS,)).to_event(1))
        a = numpyro.sample("output_bias", dist.Laplace(0., 1.))
        hidden = jax.nn.sigmoid(x@w+b)
        hazard_logits = hidden@v+a
        numpyro.sample("monthly_churn", dist.Binomial(total_count=at_risk, logits=hazard_logits), obs=churned)

    # Break hidden-unit symmetry while initializing the mean near observed
    # TRAINING churn. No held-out response enters initialization or fitting.
    rng = np.random.default_rng(seed)
    init_w = rng.normal(0, .15, (n_features, HIDDEN_UNITS))
    init_v = rng.normal(0, .2, HIDDEN_UNITS)
    pooled = (float(churned.sum())+.5)/(float(at_risk.sum())+1)
    initial = {"hidden_weights": jnp.asarray(init_w), "hidden_bias": jnp.zeros(HIDDEN_UNITS),
               "output_weights": jnp.asarray(init_v), "output_bias": jnp.asarray(logit(pooled)-.5*init_v.sum())}
    guide = AutoNormal(specification, init_loc_fn=init_to_value(values=initial), init_scale=.05)
    svi = SVI(specification, guide, ClippedAdam(.01, clip_norm=10.), Trace_ELBO())
    result = svi.run(jax.random.PRNGKey(seed), steps, progress_bar=False)
    losses = np.asarray(result.losses)
    if not np.isfinite(losses).all():
        raise RuntimeError("Nonfinite Bayesian-network variational objective")
    samples = guide.sample_posterior(jax.random.PRNGKey(seed+1), result.params, sample_shape=(POSTERIOR_DRAWS,))
    draws = {k: np.asarray(v) for k, v in samples.items()}
    if not all(np.isfinite(v).all() for v in draws.values()):
        raise RuntimeError("Nonfinite Bayesian-network posterior")
    mean_hazard = network_hazards(np.asarray(x), draws).mean(axis=0)
    expected = np.asarray(at_risk)*mean_hazard
    variance = np.maximum(np.asarray(at_risk)*mean_hazard*(1-mean_hazard), 1e-9)
    diagnostics = {
        "n_training_risk_sets": len(risk),
        "initial_loss_mean": round(float(losses[:250].mean()), 8),
        "final_loss_mean": round(float(losses[-250:].mean()), 8),
        "final_two_window_relative_loss_change": round(float(abs(losses[-250:].mean()-losses[-500:-250].mean())/max(abs(losses[-250:].mean()),1)), 8),
        "training_churn_pearson_dispersion": round(float(np.sum((np.asarray(churned)-expected)**2/variance)/max(len(risk)-73,1)), 8),
        "actual_backend": jax.default_backend(), "actual_x64": bool(jax.config.x64_enabled),
        "finite_objective": True, "finite_posterior": True,
        "convergence_limitation": "A finite, stable variational objective is not proof of posterior convergence or calibrated uncertainty; AutoNormal is an approximation.",
    }
    return draws, diagnostics


def forecast_retention(draws: dict, future: pd.DataFrame, remaining: float) -> np.ndarray:
    """Recursive expected survivors from the last TRAINING count; no future counts."""
    if remaining < 0:
        raise ValueError("Remaining membership cannot be negative")
    hazard = network_hazards(_features(future), draws)
    return remaining*np.cumprod(1-hazard, axis=1)


def run_benchmark(frame: pd.DataFrame, outputdir: Path, seed: int = 20261116, steps: int = MIN_STEPS) -> dict:
    """Fit once through September 2025 and score Oct–Dec recursively.

    A fixed scoring window and minimum optimization budget prevent silently
    changing the release comparison. The main LTV model does not consume these
    predictions; they are an explicitly separate methodological benchmark.
    """
    if steps < MIN_STEPS:
        raise ValueError(f"The Orduz benchmark requires at least {MIN_STEPS} SVI steps")
    f = _validate_panel(frame)
    train = f[f.calendar_month < TRAINING_CUTOFF].copy()
    heldout = f[(f.calendar_month >= TRAINING_CUTOFF) & (f.calendar_month < SCORING_END)].copy()
    if train.empty or set(heldout.calendar_month) != {"2025-10-01", "2025-11-01", "2025-12-01"}:
        raise ValueError("The benchmark requires training data and all three fixed holdout months")
    outputdir = Path(outputdir)
    input_path = outputdir/"tables"/"cohort_age_summary.csv"
    if not input_path.is_file():
        raise ValueError("Benchmark requires the saved source-derived tables/cohort_age_summary.csv")
    saved = _validate_panel(pd.read_csv(input_path))
    if _frame_hash(f) != _frame_hash(saved):
        raise ValueError("Benchmark frame differs from the saved source-derived cohort table")
    draws, diagnostics = _fit_posterior(train, seed+300, steps)
    records = []
    for key, g in train.groupby(KEYS, sort=True):
        actual = heldout[(heldout.cohort_month == key[0]) & (heldout.channel == key[1]) &
                         (heldout.primary_need == key[2])].sort_values("age_month")
        if actual.empty:
            continue
        last = g.iloc[-1]
        if str(last.calendar_month) != "2025-09-01":
            raise ValueError("Eligible benchmark cells must have a September risk-set origin")
        predictions = forecast_retention(draws, actual, float(last.n_retained))
        for j, (_, row) in enumerate(actual.iterrows()):
            records.append({"cohort_month": key[0], "channel": key[1], "primary_need": key[2],
                            "age_month": int(row.age_month), "calendar_month": row.calendar_month,
                            "origin_retained": int(last.n_retained), "actual_retained": int(row.n_retained),
                            "pred_retained_bnn": float(predictions[:, j].mean()),
                            "pred_retained_bnn_p05": float(np.quantile(predictions[:, j], .05)),
                            "pred_retained_bnn_p95": float(np.quantile(predictions[:, j], .95))})
    result = pd.DataFrame(records).sort_values(KEYS+["age_month"]).reset_index(drop=True)
    if result.empty:
        raise ValueError("No preexisting cohort cells are eligible for the benchmark")
    tables = outputdir/"tables"
    tables.mkdir(parents=True, exist_ok=True)
    table_path = tables/"orduz_benchmark.csv"
    result.to_csv(table_path, index=False, float_format="%.10f", lineterminator="\n")
    summary = {
        "model": "Orduz-derived Bayesian neural conditional-churn benchmark",
        "role": "Separate retention-only comparison; does not determine executive LTV or cash payback.",
        "source": "https://juanitorduz.github.io/revenue_retention_numpyro/",
        "implementation": "Direct NumPyro/JAX implementation of two dense sigmoid layers, mathematically equivalent to the stated Flax architecture; not a verbatim reproduction of the tutorial.",
        "architecture": {"input_features": FEATURE_NAMES, "input_dimension": len(FEATURE_NAMES),
                         "hidden_units": HIDDEN_UNITS, "hidden_activation": "sigmoid", "output_activation": "sigmoid", "parameter_count": 73},
        "priors": "Independent Laplace(location=0, scale=1) on every hidden/output weight and bias.",
        "likelihood": "Monthly churn count ~ Binomial(previous observed survivors, network churn probability). Only positive observed risk sets enter fitting.",
        "adaptations": ["Conditional churn replaces the tutorial's original-cohort Binomial active-count likelihood to respect absorbing contractual renewals.",
                        "Fixed scaling and need/channel indicators replace the tutorial's original feature preprocessing.",
                        "This comparison fits retention only; the main report separately explains its survival and revenue models."],
        "training_last_calendar_month": "2025-09-01", "training_cutoff_exclusive": TRAINING_CUTOFF,
        "held_out_calendar_months": ["2025-10-01", "2025-11-01", "2025-12-01"],
        "new_holdout_cohorts_excluded": True,
        "forecast_origin": "Each eligible cell's September count; all three months are forecast recursively without conditioning on held-out survivors.",
        "n_cells": len(result), "retention_mae": float(abs(result.actual_retained-result.pred_retained_bnn).mean()),
        "retention_wape": float(abs(result.actual_retained-result.pred_retained_bnn).sum()/max(result.actual_retained.sum(),1)),
        "inference": {"method": "SVI AutoNormal", "optimizer": "ClippedAdam", "learning_rate": .01,
                      "clip_norm": 10., "steps": steps, "seed": seed+300, "posterior_draws": POSTERIOR_DRAWS},
        "diagnostics": diagnostics,
        "interval_scope": "5th–95th percentiles of expected survivor counts over approximate posterior parameter draws, excluding future Bernoulli process noise; not predictive coverage intervals.",
        "limitations": ["One fixed three-month historical holdout is not broad external validation.",
                        "A flexible fitted hazard does not identify individual latent churn propensities or causal retention-treatment effects.",
                        "Variational inference may understate uncertainty; hidden-unit weights are not direct managerial effect sizes.",
                        "Comparative performance is reported whether or not the network outperforms the main survival model."],
        "training_data_sha256": _frame_hash(train), "scoring_data_sha256": _frame_hash(heldout),
        "table_sha256": hashlib.sha256(table_path.read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": {name: importlib.metadata.version(name) for name in ["numpy", "scipy", "jax", "jaxlib", "numpyro"]},
    }
    _json(outputdir/"benchmark_summary.json", summary)
    _json(outputdir/"benchmark_manifest.json", {
        "input_hashes": {"tables/cohort_age_summary.csv": hashlib.sha256(input_path.read_bytes()).hexdigest()},
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "output_hashes": {name: hashlib.sha256((outputdir/name).read_bytes()).hexdigest()
                          for name in ["tables/orduz_benchmark.csv", "benchmark_summary.json"]},
    })
    return summary


def validate_benchmark(outputdir: Path) -> dict:
    """Reject stale or edited comparison outputs independently of the main model."""
    outputdir = Path(outputdir)
    path = outputdir/"benchmark_manifest.json"
    if not path.is_file():
        raise ValueError("Missing benchmark manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if set(manifest.get("input_hashes",{})) != {"tables/cohort_age_summary.csv"}:
        raise ValueError("Unexpected benchmark input contract")
    if set(manifest.get("output_hashes",{})) != {"tables/orduz_benchmark.csv", "benchmark_summary.json"}:
        raise ValueError("Unexpected benchmark output contract")
    if manifest.get("code_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Benchmark implementation changed; rerun the comparison")
    for kind in ["input_hashes", "output_hashes"]:
        for name, digest in manifest[kind].items():
            file = outputdir/name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Benchmark {kind} mismatch: {name}")
    return {"status": "passed", "files_checked": 3}


def validate_retention_comparison(outputdir: Path, expected_cells: int | None = None) -> dict:
    """A model comparison is meaningful only for identical held-out observations."""
    outputdir = Path(outputdir)
    main = pd.read_csv(outputdir/"tables"/"backtest.csv")
    neural = pd.read_csv(outputdir/"tables"/"orduz_benchmark.csv")
    keys = KEYS+["age_month", "calendar_month"]
    required = keys+["actual_retained"]
    for label, frame in [("main",main),("neural",neural)]:
        if set(required)-set(frame):
            raise ValueError(f"{label} retention comparison lacks required columns")
        if frame.duplicated(keys).any():
            raise ValueError(f"{label} retention comparison has duplicate observations")
        if frame.empty or not np.isfinite(frame.actual_retained.to_numpy(dtype=float)).all():
            raise ValueError(f"{label} retention comparison has missing actual counts")
    joined = main[required].merge(neural[required],on=keys,how="outer",suffixes=("_main","_neural"),indicator=True,validate="one_to_one")
    if not (joined._merge == "both").all():
        raise ValueError("Retention comparisons use different cohort/need/channel/age/calendar observations")
    if not np.array_equal(joined.actual_retained_main,joined.actual_retained_neural):
        raise ValueError("Retention comparisons disagree on actual held-out counts")
    if expected_cells is not None and len(joined) != expected_cells:
        raise ValueError(f"Expected {expected_cells} comparison cells, found {len(joined)}")
    return {"status":"passed","matched_cells":len(joined),"identical_actual_counts":True}
