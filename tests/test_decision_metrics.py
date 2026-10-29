"""Independent counterexamples for partition quality and causal CAC denominators."""
import numpy as np
import pandas as pd
import pytest

from cohort_lab.decision_metrics import segmentation_objective, cac_reconciliation


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


def experiment(exp="x", nt=100, nc=50, bt=20, bc=5, st=300, sc=20):
    arms = pd.DataFrame([dict(experiment_id=exp, arm=arm, channel="search", primary_need="save_time",
        assigned_at="2025-01-01", followup_end_at="2025-02-01", followup_days=31,
        n_assigned=n, n_buyers=b, media_spend=s, contribution=v)
        for arm, n, b, s, v in [("treatment", nt, bt, st, 1000), ("control", nc, bc, sc, 100)]])
    k = nt/nc
    effects = pd.DataFrame([dict(experiment_id=exp, incremental_buyers=bt-k*bc,
        incremental_media_spend=st-k*sc, incremental_contribution=1000-k*100,
        incremental_contribution_after_media=1000-k*100-st+k*sc)])
    return arms, effects


def test_unequal_arms_and_nonzero_control_cost_change_both_sides_of_bridge():
    r = cac_reconciliation(*experiment()).iloc[0]
    assert r.expected_buyers_without_tested_campaign == 10
    assert r.incremental_buyers == 10 and r.incremental_media_spend == 260
    assert r.treatment_media_cac == 15
    assert r.incremental_spend_per_treated_buyer == 13
    assert r.incremental_media_cac == 26
    assert r.incremental_buyers_se == pytest.approx(100*np.sqrt(.2*.8/100+.1*.9/50))


def test_near_zero_lift_does_not_manufacture_finite_upper_cac_bound():
    r = cac_reconciliation(*experiment(bt=11)).iloc[0]
    assert r.incremental_buyers == 1 and r.icac_interval_status == "unbounded"
    assert np.isnan(r.icac_ci_upper) and r.icac_ci_lower > 0
    zero = cac_reconciliation(*experiment(bt=10)).iloc[0]
    assert np.isnan(zero.incremental_media_cac) and np.isnan(zero.icac_ci_upper)


def test_pool_sums_standardized_effects_instead_of_aggregating_arm_rates():
    a, ea = experiment("x")
    b, eb = experiment("y", nt=50, nc=100, bt=15, bc=20, st=200, sc=40)
    r = cac_reconciliation(pd.concat([a, b]), pd.concat([ea, eb])).iloc[-1]
    assert r.expected_buyers_without_tested_campaign == 20  # 2*5 + .5*20, not 25.
    assert r.incremental_buyers == 15 and r.incremental_media_spend == 440
    assert r.incremental_media_cac == pytest.approx(440/15)
    assert np.isnan(r.followup_days)


def test_bridge_rejects_inconsistent_saved_effects():
    arms, effects = experiment()
    effects.loc[0, "incremental_buyers"] += 1
    with pytest.raises(ValueError, match="saved intention-to-treat"):
        cac_reconciliation(arms, effects)
