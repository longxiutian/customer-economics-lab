"""Independent counterexamples for partition quality and causal CAC denominators."""
import numpy as np
import pandas as pd
import pytest

from cohort_lab.decision_metrics import segmentation_objective, channel_value_decision


def test_course_partition_example_moves_variation_between_cells():
    profiles = []
    for scheme, cells in [("dma", [[20, 80], [30, 70]]), ("demographic", [[20, 30], [70, 80]])]:
        for i, values in enumerate(cells):
            profiles.append(dict(scheme=scheme, segment=str(i), n=2, mean_contribution=np.mean(values), variance=np.var(values)))
    comparison = pd.DataFrame([dict(scheme=s, n_customers=4, n_groups=2, weighted_within_variance=w,
        pooled_variance=650, pooled_cohort_centered_variance=650, cohort_centered_within_variance=w)
        for s, w in [("dma", 650), ("demographic", 25)]])
    result = segmentation_objective(comparison, pd.DataFrame(profiles)).set_index("scheme")
    assert result.loc["dma", "between_variance"] == 0
    assert result.loc["demographic", "between_variance"] == 625
    assert result.loc["demographic", "between_share"] == pytest.approx(625/650)
    assert (result.within_variance + result.between_variance == result.total_variance).all()


def test_partition_uses_customer_weights_and_rejects_different_complexity():
    profile = pd.DataFrame([dict(scheme="s", n=3, mean_contribution=0, variance=0), dict(scheme="s", n=1, mean_contribution=8, variance=0)])
    comparison = pd.DataFrame([dict(scheme="s", n_customers=4, n_groups=2, weighted_within_variance=0,
        pooled_variance=12, pooled_cohort_centered_variance=12, cohort_centered_within_variance=0)])
    r = segmentation_objective(comparison, profile).iloc[0]
    assert r.pooled_mean == 2 and r.between_variance == 12
    comparison.loc[1] = dict(comparison.iloc[0], scheme="other", n_groups=3)
    profile = pd.concat([profile, profile.assign(scheme="other")])
    with pytest.raises(ValueError, match="complexity"):
        segmentation_objective(comparison, profile)


def test_value_join_uses_pre_cac_value_once_and_requires_matching_cell():
    cac=pd.DataFrame([dict(test_id="a",value_cohort_month="2025-07-01",channel="search",primary_need="save_time",incremental_buyers=60,incremental_spend=10000,icac=10000/60)])
    value=pd.DataFrame([dict(cohort_month="2025-07-01",channel="search",primary_need="save_time",n_acquired=80,observed_months=6,horizon_months=12,forecast_share=.4,ltv_before_cac_mean=300,ltv_before_cac_p05=280,ltv_before_cac_p95=320,net_ltv_mean=200,cac=100)])
    result=channel_value_decision(cac,value).iloc[0]
    assert result.planning_net_value==8000
    assert result.value_less_icac==pytest.approx(300-10000/60)
    # Historic CAC/net LTV is irrelevant to the prospective acquisition subtraction.
    value.net_ltv_mean=-999;value.cac=1299
    assert channel_value_decision(cac,value).iloc[0].planning_net_value==8000
    value.channel="partner"
    with pytest.raises(ValueError,match="matching"):
        channel_value_decision(cac,value)
