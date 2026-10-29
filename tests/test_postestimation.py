"""Frozen-draw splicing and reconciliation fail-closed checks."""
import json
import numpy as np
import pandas as pd
import pytest
from cohort_lab import postestimation as p
from cohort_lab.model import DRAWS, HORIZON, discounted_value, cash_payback


def test_observed_history_is_fixed_and_forecast_starts_from_last_survivors(monkeypatch):
    frame = pd.DataFrame([dict(age_month=a, n_retained=n, net_revenue=r, contribution=c)
                          for a, n, r, c in [(0, 10, 100, 40), (1, 6, 90, 30)]])
    calls = []
    def future(draws, row, ages, remaining):
        calls.append((ages, remaining))
        return np.full((DRAWS, len(ages)), 3.), np.full((DRAWS, len(ages)), 20.)
    monkeypatch.setattr(p, "_future", future)
    monkeypatch.setattr(p, "_economic_ratios", lambda *args: (np.full(10, .9), np.full(10, .5)))
    n, revenue, contribution, length = p.cell_paths(frame, {}, frame)
    assert length == 2 and calls == [(list(range(2, 12)), 6.)]
    np.testing.assert_array_equal(n[0, :2], [10, 6])
    np.testing.assert_array_equal(contribution[0], [40, 30] + [10]*10)
    assert revenue[0, 2] == 18
    assert discounted_value(contribution)[0] == pytest.approx(sum(c/1.01**(a+1) for a, c in enumerate([40, 30]+[10]*10)))
    assert cash_payback(contribution[0], 65) + 1 == 2
    assert n.shape == (DRAWS, HORIZON)


def test_reconciliation_rejects_changed_value():
    p._same([1., np.nan], [1., np.nan], "matching")
    with pytest.raises(ValueError, match="reconciliation failed"):
        p._same([1., 2.], [1., 2.01], "changed")


@pytest.mark.parametrize("case", ["maturity", "experimental", "missing_comparator", "changed_value"])
def test_complete_breakout_selection_and_reconciliation(tmp_path, monkeypatch, case):
    from cohort_lab import report
    monkeypatch.setattr(p, "validate_analysis", lambda *_: None)
    monkeypatch.setattr(report, "_validate_model_outputs", lambda *_: None)
    monkeypatch.setattr(p, "_validate", lambda frame: frame)
    monkeypatch.setattr(p, "DRAWS", 2)
    monkeypatch.setattr(p, "_future", lambda draws, row, ages, remaining:
                        (np.full((2, len(ages)), 10.), np.full((2, len(ages)), 100.)))
    monkeypatch.setattr(p, "_economic_ratios", lambda frame, row, ages:
                        (np.full(len(ages), .8), np.full(len(ages), .4)))
    tables = tmp_path / "tables"; tables.mkdir()
    months = [("2024-06-01", 12), ("2024-07-01", 12), ("2025-06-01", 6),
              ("2025-07-01", 6), ("2025-08-01", 5)]
    if case == "missing_comparator": months.remove(("2024-07-01", 12))
    panel, costs, values, curves, exclusions, company = [], [], [], [], [], []
    discounted = 4 / 1.01 ** np.arange(1, 13)
    total = float(discounted.sum())
    for cohort, length in months:
        company.append(dict(cohort_month=cohort, age_month=0, acquisition_spend=80))
        for age in range(12):
            curves.append(dict(cohort_month=cohort, age_month=age, n_retained_mean=40,
                n_retained_p05=40, n_retained_p95=40, contribution_mean=160,
                contribution_p05=160, contribution_p95=160, net_revenue_mean=320,
                cumulative_after_acquisition=160*(age+1)-80))
        for channel in ["partner", "search"]:
            for need in ["build_skill", "save_time"]:
                key = dict(cohort_month=cohort, channel=channel, primary_need=need)
                panel.extend(key | dict(age_month=a, n_acquired=10, n_retained=10,
                    net_revenue=80, contribution=40) for a in range(length))
                costs.append(key | dict(n_acquired=10, acquisition_spend=20, cac=2))
                n_excluded = int(case == "experimental" and cohort == "2025-07-01"
                                 and channel == "partner" and need == "build_skill")
                exclusions.append(key | dict(age_month=0, n_acquired=10-n_excluded))
                observed = float(discounted[:length].sum())
                values.append(key | dict(n_acquired=10, acquisition_spend=20, cac=2,
                    observed_months=length, horizon_months=12, ltv_before_cac_mean=total,
                    ltv_before_cac_p05=total, ltv_before_cac_p95=total, net_ltv_mean=total-2,
                    net_ltv_p05=total-2, net_ltv_p95=total-2, ltv_to_cac_mean=total/2,
                    payback_age=0, payback_month=1, payback_status="observed",
                    forecast_share=(total-observed)/total,
                    p_expected_cash_balance_nonnegative_at_horizon=1,
                    cash_payback_recrosses_below_cost=False,
                    observed_discounted_contribution_per_customer=observed))
    if case == "changed_value": values[0]["net_ltv_mean"] += .01
    for name, rows in [("cohort_age_summary", panel), ("cohort_acquisition_costs", costs),
                       ("cohort_valuation_by_segment", values), ("forecast_curve", curves),
                       ("cohort_age_ex_tests", exclusions), ("cohort_cash_economics", company)]:
        pd.DataFrame(rows).to_csv(tables / (name + ".csv"), index=False)
    for name in ["posterior_draws.json", "model_manifest.json"]:
        (tmp_path / name).write_text(json.dumps({}), encoding="utf-8")
    expected_error = {"changed_value": "reconciliation failed", "missing_comparator": "comparator is unavailable"}
    if case in expected_error:
        with pytest.raises(ValueError, match=expected_error[case]): p.build_postestimation(tmp_path)
        assert not (tmp_path / "postestimation_manifest.json").exists()
    else:
        receipt = p.build_postestimation(tmp_path)
        month = "06" if case == "experimental" else "07"
        assert receipt["selected_cohort"] == f"2025-{month}-01"
        assert receipt["comparison_cohort"] == f"2024-{month}-01"
        result = pd.read_csv(tables / "strategic_segment_breakout.csv")
        assert len(result) == 8 and set(result.observed_months) == {6, 12}
        assert receipt["reconciliation"]["cells"] == 20
