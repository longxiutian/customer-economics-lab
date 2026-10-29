"""Independent statistical identities and fail-closed diagnostic checks for v2."""
import numpy as np
import pandas as pd
import pytest

from cohort_lab import model


def _draws(alpha=1.08, beta=3.67):
    d = model.DRAWS
    mean = np.zeros((d,5)); mean[:,0] = np.log(alpha/beta)
    concentration = np.zeros((d,4)); concentration[:,0] = np.log(alpha+beta)
    revenue = np.zeros((d,6)); revenue[:,0] = np.log(.5)
    return {"mean_beta":mean,"concentration_beta":concentration,
            "cohort_scale":np.zeros(d),"cohort_z":np.zeros((d,24)),
            "revenue_beta":revenue,"revenue_shape":np.ones(d)}


def _panel():
    return pd.DataFrame([dict(cohort_month="2024-01-01",cohort_index=0,age_month=age,
                              calendar_month=f"2024-{age+1:02d}-01",channel="search",primary_need="save_time",
                              n_acquired=100,n_retained=100-10*age,
                              gross_payment_revenue=(100-10*age)*50,net_revenue=(100-10*age)*49,
                              contribution=(100-10*age)*20) for age in range(4)])


def test_sbg_hazards_reproduce_integrated_survival_and_decline():
    alpha,beta = 1.08,3.67
    rows = pd.DataFrame([{**_panel().iloc[0].to_dict(),"age_month":age} for age in range(1,25)])
    hazard = model._hazard_draws(_draws(alpha,beta),rows)[0]
    survival = model.sbg_survival(alpha,beta,np.arange(25))
    assert survival[0] == pytest.approx(1)
    np.testing.assert_allclose(np.cumprod(1-hazard),survival[1:],rtol=1e-12)
    np.testing.assert_allclose(hazard,alpha/(alpha+beta+np.arange(24)))
    assert (np.diff(hazard)<0).all()


def test_conditional_forecast_matches_beta_survival_ratio_after_observed_prefix():
    alpha,beta = 1.08,3.67
    ages = [5,6,7]
    remaining = 60
    forecast,revenue = model._future(_draws(alpha,beta),_panel().iloc[0],ages,remaining)
    expected = remaining*model.sbg_survival(alpha,beta,np.asarray(ages))/model.sbg_survival(alpha,beta,4)
    np.testing.assert_allclose(forecast,np.tile(expected,(model.DRAWS,1)),rtol=1e-12)
    np.testing.assert_allclose(revenue,forecast*50)


def test_beta_parameterization_has_correct_mean_and_residual_variance():
    alpha,beta = 1.08,3.67
    a,b,mu,phi = model._sbg_parameters(_draws(alpha,beta),_panel().iloc[:1])
    np.testing.assert_allclose(a,alpha); np.testing.assert_allclose(b,beta)
    np.testing.assert_allclose(mu,alpha/(alpha+beta))
    expected_variance = alpha*beta/((alpha+beta)**2*(alpha+beta+1))
    np.testing.assert_allclose(mu*(1-mu)/(phi+1),expected_variance)


def test_retention_features_cannot_access_latent_truth_or_post_acquisition_signals():
    frame = _panel()
    before = model._retention_features(frame)
    frame["theta"] = .999
    frame["latent_class"] = "fragile"
    frame["value_rating"] = 1
    frame["n_retained"] = 0
    after = model._retention_features(frame)
    for original,changed in zip(before,after):
        np.testing.assert_array_equal(original,changed)


@pytest.mark.parametrize("bad_field",["max_r_hat","min_ess","retention_pearson_dispersion","revenue_pearson_dispersion"])
def test_nonfinite_diagnostics_block_forecasting(tmp_path,monkeypatch,bad_field):
    tables = tmp_path/"tables"; tables.mkdir()
    frame = _panel()
    frame.to_csv(tables/"cohort_age_summary.csv",index=False)
    pd.DataFrame([dict(cohort_month="2024-01-01",channel="search",primary_need="save_time",
                       n_acquired=100,cac=50,acquisition_spend=5000)]).to_csv(tables/"cohort_acquisition_costs.csv",index=False)
    pd.DataFrame([dict(cohort_month="2024-01-01",age_month=0,n_acquired=100,acquisition_spend=5000)]).to_csv(tables/"cohort_cash_economics.csv",index=False)
    good = dict(max_r_hat=1.001,min_ess=1000,divergences=0,
                retention_pearson_dispersion=1.,revenue_pearson_dispersion=1.,parameter_summary=[])
    bad = {**good,bad_field:float("nan")}
    monkeypatch.setattr("cohort_lab.analysis.validate_analysis",lambda *a:{"status":"passed"})
    monkeypatch.setattr(model,"_backtest",lambda *a:(pd.DataFrame(),{"diagnostic":good}))
    monkeypatch.setattr(model,"_valuation_backtest",lambda *a:(pd.DataFrame(),{"diagnostic":good}))
    monkeypatch.setattr(model,"_posterior",lambda *a:(_draws(),bad))
    def unsafe_release(*args,**kwargs):
        raise AssertionError("Nonfinite diagnostics reached valuation")
    monkeypatch.setattr(model,"_valuation_record",unsafe_release)
    with pytest.raises(RuntimeError,match="diagnostic|finite"):
        model.fit_and_forecast(tmp_path)
