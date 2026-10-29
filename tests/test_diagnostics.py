"""Independent timing, denominator and standardization counterexamples."""
import numpy as np
import pandas as pd
import pytest
from test_data_sql import hand_data, _read, _write, _seal
from cohort_lab.analysis import build_views
from cohort_lab.diagnostics import standardized_contrast


def test_pre_renewal_window_missingness_ties_and_censored_outcomes(hand_data, tmp_path):
    events = [dict(event_id=str(i), person_id=pid, occurred_at=when, event_type=kind, platform="web")
              for i, (pid, when, kind) in enumerate([
                  ("A", "2024-01-03 08:00:00", "onboarding_started"),
                  ("A", "2024-01-30 08:59:59", "core_action"),
                  ("B", "2024-01-30 09:00:00", "core_action"),
                  ("B", "2024-02-10 12:00:00", "onboarding_completed")])]
    responses = [dict(response_id=rid, person_id=pid, submitted_at=when,
                      journey_stage=stage, ease_rating=4, value_rating=3, main_difficulty=category)
                 for rid, pid, when, stage, category in [
                     ("b", "A", "2024-01-24 10:00:00", "onboarding", "finding_time"),
                     ("a", "A", "2024-01-24 10:00:00", "onboarding", "none"),
                     ("c", "B", "2024-01-24 10:00:00", "onboarding", ""),
                     ("d", "B", "2024-01-20 10:00:00", "ongoing_use", "finding_features"),
                     ("e", "C", "2024-03-30 09:00:00", "onboarding", "getting_started")]]
    _write(hand_data, "product_events.csv", events); _write(hand_data, "feedback.csv", responses); _seal(hand_data)
    out = tmp_path / "out"; build_views(hand_data, out)
    f = pd.read_csv(out / "tables/friction_subjects.csv").set_index("person_id")
    assert set(f.index) == {"A", "B", "C"}  # Treatment/control buyers stay excluded.
    assert f.loc["A", "early_core_actions"] == 1
    assert f.loc["B", "early_core_actions"] == 0
    assert f.loc["B", "onboarding_completions"] == 0
    assert f.loc["A", "survey_group"] == "none" and f.loc["A", "response_id"] == "a"
    assert f.loc["B", "survey_group"] == "unanswered_item"
    assert f.loc["C", "survey_group"] == "no_response"
    assert f.loc["A", "retained_age1"] == 1 and f.loc["B", "retained_age1"] == 0
    assert pd.isna(f.loc["C", "retained_age1"])  # Pending first renewal.
    assert f.retained_age5.isna().all() and f.contribution_ages1_5.isna().all()
    assert f.loc["A", "in_window_refunds"] == 1  # Refund does not erase membership.
    assert f.loc["A", "contribution_age0"] == 55  # Includes the dated refund.
    summary = pd.read_csv(out / "tables/friction_segment_summary.csv")
    assert (summary.groupby("scheme").n_acquired.sum() == 3).all()
    features = ["onboarding_completions", "early_core_actions", "early_support_contacts", "response_id", "survey_group"]
    before = f[features].copy()
    # A later response/event cannot retroactively become an early feature.
    events.append(dict(event_id="late", person_id="B", occurred_at="2024-03-15 09:00:00", event_type="core_action", platform="web"))
    responses.append(dict(response_id="late", person_id="B", submitted_at="2024-03-15 10:00:00", journey_stage="onboarding", ease_rating=1, value_rating=1, main_difficulty="finding_time"))
    _write(hand_data, "product_events.csv", events); _write(hand_data, "feedback.csv", responses); _seal(hand_data)
    build_views(hand_data, out)
    pd.testing.assert_frame_equal(before, pd.read_csv(out / "tables/friction_subjects.csv").set_index("person_id")[features])


def test_standardization_recovers_within_stratum_gap_and_reports_missing_support():
    rows = []
    # Crude gap +26 points; both stratum-specific gaps are -10 points.
    for channel, group, n, retained in [("high", "target", 80, 56), ("low", "target", 20, 2),
                                        ("high", "reference", 20, 16), ("low", "reference", 80, 16)]:
        rows += [dict(acquisition_year="2024", channel=channel, primary_need="same", signal=group,
                      outcome=int(i < retained)) for i in range(n)]
    f = pd.DataFrame(rows)
    result = standardized_contrast(f, "signal", "target", "reference", "outcome")
    assert result["crude_difference"] == pytest.approx(.26)
    assert result["difference"] == pytest.approx(-.1)
    assert result["coverage"] == 1 and result["n_strata"] == 2
    assert result["ci_lower"] < result["difference"] < result["ci_upper"]
    # Missing reference support is excluded transparently, never imputed.
    f.loc[f.channel == "low", "signal"] = "target"
    result = standardized_contrast(f, "signal", "target", "reference", "outcome")
    assert result["coverage"] == .5 and result["n_strata"] == 1
    assert result["difference"] == pytest.approx(-.1)
    result = standardized_contrast(f.iloc[:0], "signal", "target", "reference", "outcome")
    assert result["coverage"] == 0 and np.isnan(result["difference"])


def test_mature_non_survivors_keep_zero_retention_and_recorded_refunds(hand_data, tmp_path):
    periods = _read(hand_data / "subscription_periods.csv")
    for row in periods:
        if row["period_id"] == "C4":
            row.update(renewal_outcome="cancelled", cancellation_effective_at="2024-04-03 08:00:00")
    _write(hand_data, "subscription_periods.csv", periods)
    transactions = _read(hand_data / "transactions.csv")
    transactions.append(dict(transaction_id="LATE_REF", person_id="A", period_id="A2",
        occurred_at="2024-02-20 09:00:00", transaction_type="refund", related_transaction_id="TA2",
        order_id="OTA2", charge_type="subscription", gross_amount="0.00", discount_amount="0.00",
        refund_amount="10.00", variable_cost="0.00"))
    _write(hand_data, "transactions.csv", transactions)
    _seal(hand_data, as_of="2024-07-01T00:00:00Z")
    out = tmp_path / "mature"; build_views(hand_data, out)
    people = pd.read_csv(out / "tables/friction_subjects.csv").set_index("person_id")
    # A renews once with a later same-cycle refund, then exits at age 2.
    # The source contract keeps refunds in their original payment cycle.
    # Ages 1–5 include 70 - 10 = 60, followed by zeros after exit.
    assert people.loc["A", "retained_age5"] == 0
    assert people.loc["A", "contribution_ages1_5"] == 60
    assert people.loc["B", "retained_age5"] == 0
    assert people.loc["B", "contribution_ages1_5"] == 0
    assert pd.isna(people.loc["C", "retained_age5"])
    summary = pd.read_csv(out / "tables/friction_segment_summary.csv")
    row = summary.query("scheme == 'onboarding' and segment == 'not_recorded'").iloc[0]
    assert row.n_age5_observed == 2 and row.n_retained_age5 == 0
    assert row.mean_contribution_ages1_5 == 30


def test_survey_month_support_excludes_unobserved_fielding_without_imputation():
    f = pd.DataFrame([dict(cohort_month=month, channel="search", primary_need="save_time", signal=signal, outcome=value)
                      for month, signal, value in [
                          ("2024-01", "response", 1), ("2024-01", "response", 0),
                          ("2024-01", "no_response", 1), ("2024-01", "no_response", 0),
                          ("2024-02", "no_response", 1), ("2024-02", "no_response", 1),
                          ("2024-02", "no_response", 1), ("2024-02", "no_response", 1)]])
    r = standardized_contrast(f, "signal", "no_response", "response", "outcome", ["cohort_month", "channel", "primary_need"])
    assert r["coverage"] == .5 and r["n_strata"] == 1
    assert r["n_target_common"] == r["n_reference_common"] == 2
    assert r["difference"] == r["crude_common_difference"] == 0
    assert r["crude_difference"] > 0  # Calendar composition would otherwise manufacture a gap.
