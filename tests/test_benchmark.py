"""Architecture, fixed transforms and chronological isolation of the BNN benchmark."""
import json

import numpy as np
import pandas as pd
import pytest

from cohort_lab.benchmark import (
    FEATURE_NAMES, MIN_STEPS, POSTERIOR_DRAWS, _features, _risk_set,
    forecast_retention, network_hazards, run_benchmark, validate_benchmark,
)


def constant_draws(hazard=.2):
    d = POSTERIOR_DRAWS
    return {"hidden_weights": np.zeros((d, len(FEATURE_NAMES), 4)),
            "hidden_bias": np.zeros((d, 4)), "output_weights": np.zeros((d, 4)),
            "output_bias": np.full(d, np.log(hazard/(1-hazard)))}


def panel():
    records = []
    for ci in [0, 17, 20, 21]:
        for age in range(24-ci):
            records.append(dict(cohort_month=str(pd.Timestamp("2024-01-01")+pd.DateOffset(months=ci))[:10],
                                cohort_index=ci, age_month=age,
                                calendar_month=str(pd.Timestamp("2024-01-01")+pd.DateOffset(months=ci+age))[:10],
                                channel="search", primary_need="save_time", n_retained=max(0,100-age*3)))
    return pd.DataFrame(records)


def prepare(folder, frame):
    (folder/"tables").mkdir(parents=True,exist_ok=True)
    frame.to_csv(folder/"tables"/"cohort_age_summary.csv",index=False)
    return folder


def test_fixed_features_are_16_dimensions_and_ignore_outcomes():
    f = panel()
    x = _features(f)
    assert x.shape == (len(f), 16)
    np.testing.assert_allclose(x[:,0], f.age_month/23)
    np.testing.assert_allclose(x[:,1], (f.cohort_index-11.5)/11.5)
    f["n_retained"] = -999999
    f["true_churn_probability"] = .999
    np.testing.assert_array_equal(x, _features(f))
    january = pd.to_datetime(f.calendar_month).dt.month == 1
    assert (x[january,5:] == 0).all()
    assert (x[~january,5:].sum(axis=1) == 1).all()


def test_network_is_nonlinear_hidden_layer_not_linear_renaming():
    from scipy.special import expit
    draws = constant_draws(.5)
    draws["hidden_weights"][:,0,0] = 2
    draws["hidden_bias"][:,0] = -.4
    draws["output_weights"][:,0] = 3
    draws["output_bias"][:] = -.7
    x = np.zeros((3,16)); x[:,0] = [-1,0,1]
    actual = network_hazards(x, draws)
    expected = expit(3*expit(2*x[:,0]-.4)-.7)
    np.testing.assert_allclose(actual, np.tile(expected,(POSTERIOR_DRAWS,1)))
    assert not np.isclose(expected[1], (expected[0]+expected[2])/2)
    np.testing.assert_array_equal(actual, network_hazards(x, draws))


def test_recursive_forecast_uses_last_training_count():
    future = panel().query("cohort_index==0 and calendar_month >= '2025-10-01'")
    pred = forecast_retention(constant_draws(), future, 80)
    np.testing.assert_allclose(pred[0], [64,51.2,40.96])
    changed = future.copy(); changed["n_retained"] = [1,0,0]
    np.testing.assert_array_equal(pred, forecast_retention(constant_draws(), changed, 80))
    assert (np.diff(pred,axis=1) <= 0).all()
    assert (forecast_retention(constant_draws(), future, 0) == 0).all()


def test_risk_sets_use_monthly_drops_not_repeated_cumulative_counts():
    f = panel().query("cohort_index == 0").iloc[:3].copy()
    f["n_retained"] = [100,80,72]
    risk = _risk_set(f)
    assert risk.previous_retained.tolist() == [100,80]
    assert risk.n_churned.tolist() == [20,8]


def test_benchmark_training_and_predictions_are_heldout_isolated(tmp_path, monkeypatch):
    seen = []
    def fake_fit(train, seed, steps):
        seen.append((train.copy(),seed,steps))
        return constant_draws(), {"finite_objective": True}
    monkeypatch.setattr("cohort_lab.benchmark._fit_posterior",fake_fit)
    f = panel()
    first = run_benchmark(f,prepare(tmp_path/"first",f))
    changed = f.copy()
    changed.loc[changed.calendar_month >= "2025-10-01","n_retained"] = 1
    second = run_benchmark(changed,prepare(tmp_path/"second",changed))
    a = pd.read_csv(tmp_path/"first"/"tables"/"orduz_benchmark.csv")
    b = pd.read_csv(tmp_path/"second"/"tables"/"orduz_benchmark.csv")
    assert all((train.calendar_month < "2025-10-01").all() for train,_,_ in seen)
    assert all(seed == 20261416 and steps == MIN_STEPS for _,seed,steps in seen)
    np.testing.assert_array_equal(a.pred_retained_bnn,b.pred_retained_bnn)
    assert not a.actual_retained.equals(b.actual_retained)
    assert first["training_data_sha256"] == second["training_data_sha256"]
    assert first["scoring_data_sha256"] != second["scoring_data_sha256"]
    assert "2025-10-01" not in set(a.cohort_month)  # New holdout acquisitions are not forecast.
    assert first["architecture"]["parameter_count"] == 73
    assert first["retention_mae"] == pytest.approx(abs(a.actual_retained-a.pred_retained_bnn).mean())
    assert json.loads((tmp_path/"first"/"benchmark_summary.json").read_text())["n_cells"] == 9
    assert validate_benchmark(tmp_path/"first")["status"] == "passed"
    manifest = json.loads((tmp_path/"first"/"benchmark_manifest.json").read_text())
    assert set(manifest["input_hashes"]) == {"tables/cohort_age_summary.csv"}
    assert set(manifest["output_hashes"]) == {"tables/orduz_benchmark.csv","benchmark_summary.json"}
    target = tmp_path/"first"/"tables"/"orduz_benchmark.csv"
    target.write_text(target.read_text()+"\n")
    with pytest.raises(ValueError,match="output_hashes mismatch"):
        validate_benchmark(tmp_path/"first")


def test_benchmark_refuses_unsaved_or_different_frame(tmp_path,monkeypatch):
    def fail_fit(*args):
        raise AssertionError("No inference before validating saved inputs")
    monkeypatch.setattr("cohort_lab.benchmark._fit_posterior",fail_fit)
    f = panel()
    with pytest.raises(ValueError,match="requires the saved"):
        run_benchmark(f,tmp_path)
    prepare(tmp_path,f)
    changed = f.copy(); changed.loc[1,"n_retained"] = 99
    with pytest.raises(ValueError,match="differs from the saved"):
        run_benchmark(changed,tmp_path)


def test_benchmark_guards_release_budget_and_window_before_fitting(tmp_path, monkeypatch):
    def fail_fit(*args):
        raise AssertionError("Must not dispatch inference for an invalid request")
    monkeypatch.setattr("cohort_lab.benchmark._fit_posterior",fail_fit)
    with pytest.raises(ValueError,match="at least 10000"):
        run_benchmark(panel(),tmp_path,steps=100)
    with pytest.raises(ValueError,match="all three"):
        run_benchmark(panel().query("calendar_month != '2025-12-01'"),tmp_path)


def test_benchmark_rejects_nonabsorbing_or_duplicate_panels(tmp_path):
    f = panel()
    f.loc[2,"n_retained"] = 101
    with pytest.raises(ValueError,match="absorbing"):
        run_benchmark(f,tmp_path)
    f = panel()
    with pytest.raises(ValueError,match="Duplicate"):
        run_benchmark(pd.concat([f,f.iloc[:1]]),tmp_path)
