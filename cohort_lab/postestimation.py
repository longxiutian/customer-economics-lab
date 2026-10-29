"""Export acquisition-cell trajectories from frozen draws, without fitting.

All 12-receipt cell values and whole-cohort paths must reconcile with the saved
baseline before selecting the latest non-experimental six-receipt cohort.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from .analysis import validate_analysis, _hash
from .model import KEYS, HORIZON, DRAWS, _validate, _future, _economic_ratios, _valuation_record, _csv


def cell_paths(frame: pd.DataFrame, draws: dict, group: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    g = group.sort_values("age_month")
    length = min(len(g), HORIZON)
    retained = np.zeros((DRAWS, HORIZON)); revenue = retained.copy(); contribution = retained.copy()
    retained[:, :length] = g.n_retained.to_numpy()[:length]
    revenue[:, :length] = g.net_revenue.to_numpy()[:length]
    contribution[:, :length] = g.contribution.to_numpy()[:length]
    if length < HORIZON:
        ages = list(range(length, HORIZON))
        n, gross = _future(draws, g.iloc[-1], ages, float(g.n_retained.iloc[-1]))
        net_ratio, contribution_ratio = _economic_ratios(frame, g.iloc[-1], ages)
        retained[:, length:] = n; revenue[:, length:] = gross * net_ratio
        contribution[:, length:] = gross * contribution_ratio
    return retained, revenue, contribution, length


def _same(actual, expected, label):
    if not np.allclose(actual, expected, rtol=1e-9, atol=1e-8, equal_nan=True):
        raise ValueError(f"Post-estimation baseline reconciliation failed: {label}")


def build_postestimation(output_dir: Path) -> dict:
    output = Path(output_dir)
    validate_analysis(output)
    # Local import avoids the report/post-estimation import cycle.
    from .report import _validate_model_outputs
    _validate_model_outputs(output)
    tables = output / "tables"
    frame = _validate(pd.read_csv(tables / "cohort_age_summary.csv"))
    draws = {k: np.asarray(v) for k, v in json.loads((output / "posterior_draws.json").read_text()).items()}
    costs = pd.read_csv(tables / "cohort_acquisition_costs.csv").set_index(KEYS)
    values = pd.read_csv(tables / "cohort_valuation_by_segment.csv").set_index(KEYS)
    company_costs = pd.read_csv(tables / "cohort_cash_economics.csv").query("age_month==0").set_index("cohort_month")
    original_curves = pd.read_csv(tables / "forecast_curve.csv")
    aggregate = {}; records = []
    for key, g in frame.groupby(KEYS, sort=True):
        n, revenue, contribution, length = cell_paths(frame, draws, g)
        n0 = int(g.n_acquired.iloc[0]); observed = np.arange(HORIZON) < length
        supported = key in costs.index and pd.notna(costs.loc[key, "cac"])
        spend = float(costs.loc[key, "acquisition_spend"]) if supported else 0.
        recomputed = _valuation_record(key, n0, spend, length, contribution, observed, supported)
        old = values.loc[key]
        for column, value in recomputed.items():
            if column == "cohort_month": continue
            if isinstance(value, str):
                if value != old[column]: raise ValueError(f"Changed baseline {column}: {key}")
            else: _same(np.nan if value is None else value, old[column], f"{key}/{column}")
        cash = (np.cumsum(contribution, axis=1) - spend) / n0
        for age in range(HORIZON):
            records.append(dict(zip(KEYS, key)) | {"age_month": age, "n_acquired": n0, "observed": bool(observed[age]),
                "retained_share_mean": float(n[:, age].mean() / n0),
                "retained_share_p05": float(np.quantile(n[:, age], .05) / n0),
                "retained_share_p95": float(np.quantile(n[:, age], .95) / n0),
                "cash_after_cac_mean": float(cash[:, age].mean()) if supported else np.nan,
                "cash_after_cac_p05": float(np.quantile(cash[:, age], .05)) if supported else np.nan,
                "cash_after_cac_p95": float(np.quantile(cash[:, age], .95)) if supported else np.nan})
        if key[0] not in aggregate:
            aggregate[key[0]] = {"n": np.zeros_like(n), "revenue": np.zeros_like(n), "contribution": np.zeros_like(n), "n0": 0}
        a = aggregate[key[0]]; a["n"] += n; a["revenue"] += revenue; a["contribution"] += contribution; a["n0"] += n0
    for cohort, a in aggregate.items():
        old = original_curves[original_curves.cohort_month == cohort].sort_values("age_month")
        for stem, quantity in [("n_retained", "n"), ("contribution", "contribution")]:
            for suffix, stat in [("mean", np.mean), ("p05", lambda x, axis: np.quantile(x, .05, axis=axis)), ("p95", lambda x, axis: np.quantile(x, .95, axis=axis))]:
                _same(stat(a[quantity], axis=0), old[stem + "_" + suffix], f"{cohort}/{stem}_{suffix}")
        _same(a["revenue"].mean(axis=0), old.net_revenue_mean, f"{cohort}/revenue")
        cash = np.cumsum(a["contribution"].mean(axis=0)) - company_costs.loc[cohort, "acquisition_spend"]
        _same(cash, old.cumulative_after_acquisition, f"{cohort}/cash")
    curves = pd.DataFrame(records)
    _csv(tables / "segment_forecast_curves.csv", curves)
    ex = pd.read_csv(tables / "cohort_age_ex_tests.csv").query("age_month==0").set_index(KEYS)
    candidates = []
    paid = values.reset_index().query("channel in ['search','partner']")
    for cohort, cells in paid.groupby("cohort_month", sort=True):
        if len(cells) != 4 or cells.observed_months.min() < 6: continue
        if all(tuple(r[k] for k in KEYS) in ex.index and ex.loc[tuple(r[k] for k in KEYS), "n_acquired"] == r.n_acquired for _, r in cells.iterrows()):
            candidates.append(cohort)
    if not candidates: raise ValueError("No non-experimental four-cell cohort with six observed receipts")
    selected = max(candidates)
    prior = (pd.Timestamp(selected) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    breakout = paid[paid.cohort_month.isin([selected, prior])].copy()
    if len(breakout) != 8: raise ValueError("Same-season strategic comparator is unavailable")
    for _, r in breakout.iterrows():
        key = tuple(r[k] for k in KEYS)
        if key not in ex.index or ex.loc[key, "n_acquired"] != r.n_acquired:
            raise ValueError("Strategic comparator contains experimental buyers")
    age5 = frame[frame.age_month == 5][KEYS + ["n_retained"]]
    breakout = breakout.merge(age5, on=KEYS, validate="one_to_one")
    breakout["retained_share_age5"] = breakout.n_retained / breakout.n_acquired
    breakout["role"] = np.where(breakout.cohort_month == selected, "latest_six_receipt", "same_month_prior_year")
    _csv(tables / "strategic_segment_breakout.csv", breakout.sort_values(KEYS))
    gap_records = []
    for (cohort, channel), cells in paid[paid.observed_months >= 6].groupby(["cohort_month", "channel"], sort=True):
        if set(cells.primary_need) != {"build_skill", "save_time"}: continue
        if not all(tuple(r[k] for k in KEYS) in ex.index and ex.loc[tuple(r[k] for k in KEYS), "n_acquired"] == r.n_acquired for _, r in cells.iterrows()): continue
        cells = cells.set_index("primary_need")
        gap_records.append({"cohort_month": cohort, "channel": channel,
                            "build_minus_save_net_value": float(cells.loc["build_skill", "net_ltv_mean"] - cells.loc["save_time", "net_ltv_mean"]),
                            "fully_observed": bool((cells.forecast_share.abs() < 1e-9).all()),
                            "max_forecast_share": float(cells.forecast_share.max())})
    _csv(tables / "strategic_rank_stability.csv", pd.DataFrame(gap_records))
    inputs = ["cohort_age_summary.csv", "cohort_acquisition_costs.csv", "cohort_cash_economics.csv", "cohort_age_ex_tests.csv",
              "cohort_valuation_by_segment.csv", "forecast_curve.csv"]
    manifest = {"version": 1, "refit": False, "selected_cohort": selected, "comparison_cohort": prior,
                "selection": "Latest four-cell paid cohort with >=6 observed receipts and no experimental buyers; compare same month one year earlier. Selection uses maturity and assignment, never economic outcomes.",
                "scope": "Acquisition channel × baseline stated need only. Observed values spliced to conditional expected forecasts from existing draws. Bands are 5th–95th parameter percentiles; fixed cost ratios and no customer-process uncertainty. Average CAC and value do not identify marginal or causal returns.",
                "reconciliation": {"status": "passed", "cells": len(values), "cohorts": len(aggregate), "rtol": 1e-9, "atol": 1e-8},
                "code_sha256": _hash(Path(__file__)), "model_code_sha256": _hash(Path(__file__).with_name("model.py")),
                "draws_sha256": _hash(output / "posterior_draws.json"), "model_manifest_sha256": _hash(output / "model_manifest.json"),
                "input_hashes": {name: _hash(tables / name) for name in inputs},
                "output_hashes": {name: _hash(tables / name) for name in ["segment_forecast_curves.csv", "strategic_segment_breakout.csv", "strategic_rank_stability.csv"]}}
    (output / "postestimation_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_postestimation(output_dir: Path) -> dict:
    output = Path(output_dir)
    m = json.loads((output / "postestimation_manifest.json").read_text())
    expected = {"segment_forecast_curves.csv", "strategic_segment_breakout.csv", "strategic_rank_stability.csv"}
    inputs = {"cohort_age_summary.csv", "cohort_acquisition_costs.csv", "cohort_cash_economics.csv", "cohort_age_ex_tests.csv", "cohort_valuation_by_segment.csv", "forecast_curve.csv"}
    if set(m["output_hashes"]) != expected or set(m["input_hashes"]) != inputs:
        raise ValueError("Unexpected post-estimation output contract")
    for key, path in [("code_sha256", Path(__file__)), ("model_code_sha256", Path(__file__).with_name("model.py")),
                      ("draws_sha256", output / "posterior_draws.json"), ("model_manifest_sha256", output / "model_manifest.json")]:
        if m[key] != _hash(path): raise ValueError(f"Post-estimation hash mismatch: {key}")
    for name, digest in {**m["input_hashes"], **m["output_hashes"]}.items():
        if _hash(output / "tables" / name) != digest: raise ValueError(f"Post-estimation hash mismatch: {name}")
    return m
