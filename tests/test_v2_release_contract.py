"""Independent checks of fair comparisons, renewal clocks and sampling starts."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cohort_lab import benchmark, model
from cohort_lab.analysis import build_views

ROOT = Path(__file__).resolve().parents[1]


def _sbg_draws():
    d = model.DRAWS
    mean = np.zeros((d,5)); mean[:,0] = np.log(.1/.9)
    concentration = np.zeros((d,4)); concentration[:,0] = np.log(4)
    revenue = np.zeros((d,6)); revenue[:,0] = np.log(.5)
    return {"mean_beta":mean,"concentration_beta":concentration,"cohort_scale":np.zeros(d),
            "cohort_z":np.zeros((d,24)),"revenue_beta":revenue,"revenue_shape":np.ones(d)}


def _neural_draws():
    d = benchmark.POSTERIOR_DRAWS
    return {"hidden_weights":np.zeros((d,16,4)),"hidden_bias":np.zeros((d,4)),
            "output_weights":np.zeros((d,4)),"output_bias":np.full(d,np.log(.1/.9))}


def test_actual_frozen_data_produces_identical_holdout_cells(tmp_path,monkeypatch):
    """Use real source/ETL observations; stub only expensive parameter estimation."""
    build_views(ROOT/"data",tmp_path)
    frame = pd.read_csv(tmp_path/"tables"/"cohort_age_summary.csv")
    monkeypatch.setattr(model,"_posterior",lambda *a,**kw:(_sbg_draws(),{}))
    monkeypatch.setattr(benchmark,"_fit_posterior",lambda *a,**kw:(_neural_draws(),{}))
    main, main_summary = model._backtest(model._validate(frame),20261116,3000)
    main.to_csv(tmp_path/"tables"/"backtest.csv",index=False)
    neural_summary = benchmark.run_benchmark(frame,tmp_path)
    eligible = frame[frame.calendar_month.le('2025-09-01')][['cohort_month','channel','primary_need']].drop_duplicates()
    expected = len(frame[frame.calendar_month.gt('2025-09-01')].merge(eligible))
    check = benchmark.validate_retention_comparison(tmp_path,expected_cells=expected)
    assert check == {"status":"passed","matched_cells":expected,"identical_actual_counts":True}
    assert main_summary["training_last_calendar_month"] == neural_summary["training_last_calendar_month"] == "2025-09-01"
    assert main_summary["held_out_calendar_months"] == neural_summary["held_out_calendar_months"]


@pytest.mark.parametrize("mutation",["missing_cell","different_count","duplicate"])
def test_comparison_refuses_unequal_scoring_observations(tmp_path,mutation):
    (tmp_path/"tables").mkdir()
    row = dict(cohort_month="2025-01-01",channel="search",primary_need="save_time",
               age_month=9,calendar_month="2025-10-01",actual_retained=20)
    main = pd.DataFrame([row,{**row,"age_month":10,"calendar_month":"2025-11-01","actual_retained":18}])
    neural = main.copy()
    if mutation == "missing_cell": neural = neural.iloc[:1]
    elif mutation == "different_count": neural.loc[0,"actual_retained"] = 19
    else: neural = pd.concat([neural,neural.iloc[:1]])
    main.to_csv(tmp_path/"tables"/"backtest.csv",index=False)
    neural.to_csv(tmp_path/"tables"/"orduz_benchmark.csv",index=False)
    with pytest.raises(ValueError,match="different|disagree|duplicate"):
        benchmark.validate_retention_comparison(tmp_path)


def _two_year_panel():
    records = []
    for ci in range(12):
        for age in range(24-ci):
            records.append(dict(cohort_month=str(pd.Timestamp("2024-01-01")+pd.DateOffset(months=ci))[:10],
                                cohort_index=ci,age_month=age,
                                calendar_month=str(pd.Timestamp("2024-01-01")+pd.DateOffset(months=ci+age))[:10],
                                channel="search",primary_need="save_time",n_acquired=100,n_retained=100,
                                gross_payment_revenue=5000.,net_revenue=4900.,contribution=2000.))
    return pd.DataFrame(records)


def test_payback_validation_accounts_for_already_future_and_never_recovered(monkeypatch):
    monkeypatch.setattr(model,"_posterior",lambda *a,**kw:(_sbg_draws(),{}))
    f = _two_year_panel()
    costs = pd.DataFrame({"cohort_month":sorted(f.cohort_month.unique()),
                          "n_acquired":100,"acquisition_spend":5000.}).set_index("cohort_month")
    costs.loc["2024-06-01","acquisition_spend"] = 1000000.  # No recovery inside twelve receipts.
    rows, summary = model._valuation_backtest(f,costs,1,3000)
    assert len(rows) == summary["n_forecast_cohorts"] == 11
    assert summary["n_payback_already_observed"] == 8
    assert summary["n_payback_after_origin"] == 2
    assert summary["n_payback_not_recovered_within_horizon"] == 1
    assert sum(summary[k] for k in ["n_payback_already_observed","n_payback_after_origin",
                                    "n_payback_not_recovered_within_horizon"]) == 11
    assert summary["n_baseline_both_recovered"] == 2
    # November has renewal history; December uses the stated 0.8 fallback and
    # recovers one receipt later. Both eligible forecasts remain in the score.
    assert summary["baseline_payback_mae_months_for_both_recovered"] == pytest.approx(.5)
    assert pd.isna(rows.loc[rows.cohort_month == "2024-06-01","actual_payback_month"]).all()


def test_acquisition_month_does_not_enter_main_renewal_likelihood(monkeypatch):
    """Trace the actual statistical specification but never execute MCMC."""
    import numpyro.handlers
    import numpyro.infer
    captured = {}
    class TracedWithoutSampling(Exception): pass
    class TraceOnly:
        def __init__(self,kernel,**kwargs): self.specification = kernel.model
        def run(self,key):
            trace = numpyro.handlers.trace(numpyro.handlers.seed(self.specification,key)).get_trace()
            captured["counts"] = np.asarray(trace["survivors"]["fn"].total_count)
            captured["observed"] = np.asarray(trace["survivors"]["value"])
            raise TracedWithoutSampling
    monkeypatch.setattr(numpyro.infer,"NUTS",lambda specification,**kwargs:SimpleNamespace(model=specification))
    monkeypatch.setattr(numpyro.infer,"MCMC",TraceOnly)
    f = _two_year_panel().query("cohort_index < 4 and age_month < 5").copy()
    f["n_retained"] = 100-10*f.age_month
    f["gross_payment_revenue"] = 50*f.n_retained
    with pytest.raises(TracedWithoutSampling):
        model._posterior(f,123,3000)
    # Four cohorts × four post-acquisition decisions, not twenty original-cohort trials.
    assert len(captured["counts"]) == 16
    np.testing.assert_array_equal(captured["counts"],np.tile([100,90,80,70],4))
    np.testing.assert_array_equal(captured["observed"],np.tile([90,80,70,60],4))


def test_chain_initialization_is_seeded_disperse_and_respects_support():
    import jax
    import jax.numpy as jnp
    import numpyro.distributions as dist
    initialize = model._dispersed_initial_strategy({"mean":jnp.array([-2.,.1]),"scale":.1,"shape":4.})
    definitions = [("mean",dist.Normal(jnp.zeros(2),1).to_event(1)),
                   ("scale",dist.HalfNormal(.25)),("shape",dist.LogNormal(1.,1.))]
    keys = jax.random.split(jax.random.PRNGKey(328),4)
    for name,distribution in definitions:
        def site(key):
            return {"type":"sample","is_observed":False,"name":name,"fn":distribution,"kwargs":{"rng_key":key}}
        first = np.asarray(initialize(site(keys[0])))
        np.testing.assert_array_equal(first,np.asarray(initialize(site(keys[0]))))
        starts = [np.asarray(initialize(site(key))) for key in keys]
        assert all(not np.array_equal(starts[0],x) for x in starts[1:])
        if name in {"scale","shape"}: assert all((x>0).all() for x in starts)
        observed = site(keys[0]); observed["is_observed"] = True
        assert initialize(observed) is None
