"""Accounting/denominator tests use an independent, hand-computed ledger."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from cohort_lab.analysis import build_views, validate_analysis
from cohort_lab.data import SCHEMAS, SCHEMA_VERSION, generate_data, validate_data


def _seal(folder, as_of="2024-04-01T00:00:00Z"):
    files = {}
    for name in SCHEMAS:
        p = folder / name
        with p.open(newline="", encoding="utf-8") as f:
            n = len(list(csv.DictReader(f)))
        files[name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "row_count": n}
    manifest = {"schema_version": SCHEMA_VERSION, "dataset_version": "fixture", "synthetic_seed": 0,
                "data_as_of": as_of, "timezone": "UTC", "currency": "USD", "files": files,
                "definitions": {"fixture": "Independent three-month hand ledger."}}
    (folder / "data_manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def _write(folder, name, rows):
    with (folder / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(SCHEMAS[name]), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SCHEMAS[name]})


def _read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def hand_data(tmp_path):
    """Jan: contribution 85 then 70; cost 120; payback age 1. No March survivors.

    Feb experiment: 2 assigned per arm, one buyer each. Treated contribution 15,
    control 6, media 8 => incremental contribution after media +1, not +7.
    """
    d = tmp_path / "sources"
    d.mkdir()
    people = []
    for pid in ["A", "B", "C", "X", "Y", "Z", "W"]:
        people.append({"person_id": pid, "record_created_at": "2023-12-01 00:00:00",
                       "attributes_recorded_at": "2023-12-02 00:00:00", "age_band": "18_34",
                       "household_type": "solo", "primary_need": "build_skill" if pid == "C" else "save_time",
                       "region": "east"})
    periods = []
    for rid, pid, month, outcome in [
        ("A1", "A", 1, "paid"), ("A2", "A", 2, "paid"), ("A3", "A", 3, "cancelled"),
        ("B1", "B", 1, "paid"), ("B2", "B", 2, "cancelled"),
        ("C3", "C", 3, "paid"), ("C4", "C", 4, "pending"),
        ("X2", "X", 2, "paid"), ("X3", "X", 3, "failed"),
        ("Y2", "Y", 2, "paid"), ("Y3", "Y", 3, "cancelled"),
    ]:
        periods.append({"period_id": rid, "subscription_id": "S"+pid, "person_id": pid,
                        "period_start": f"2024-{month:02d}-03", "period_end": f"2024-{month+1:02d}-03",
                        "renewal_due_at": f"2024-{month:02d}-03 08:00:00", "renewal_outcome": outcome,
                        "cancellation_effective_at": f"2024-{month:02d}-03 08:00:00" if outcome == "cancelled" else "",
                        "plan_tier": "standard"})
    transactions = []
    for tid, pid, period, gross, discount, cost, charge in [
        ("TA1", "A", "A1", "100.00", "10.00", "30.00", "subscription"),
        ("TAO", "A", "A1", "20.00", "0.00", "5.00", "add_on"),
        ("TA2", "A", "A2", "100.00", "0.00", "30.00", "subscription"),
        ("TB1", "B", "B1", "50.00", "0.00", "20.00", "subscription"),
        ("TC3", "C", "C3", "50.00", "0.00", "20.00", "subscription"),
        ("TX2", "X", "X2", "20.00", "0.00", "5.00", "subscription"),
        ("TY2", "Y", "Y2", "10.00", "0.00", "4.00", "subscription"),
    ]:
        month = int(period[-1])
        transactions.append({"transaction_id": tid, "person_id": pid, "period_id": period,
                             "occurred_at": f"2024-{month:02d}-{'15' if charge == 'add_on' else '03'} 09:00:00",
                             "transaction_type": "payment", "order_id": "O"+tid, "charge_type": charge,
                             "quantity": 1, "unit_price": gross, "gross_amount": gross,
                             "discount_amount": discount, "refund_amount": "0.00", "variable_cost": cost})
    transactions.append({"transaction_id": "REF", "person_id": "A", "period_id": "A1",
                         "occurred_at": "2024-01-20 09:00:00", "transaction_type": "refund",
                         "related_transaction_id": "TA1", "order_id": "OTA1", "charge_type": "subscription",
                         "gross_amount": "0.00", "discount_amount": "0.00", "refund_amount": "20.00", "variable_cost": "0.00"})
    costs = [
        {"campaign_id": "JAN", "spend_date": "2024-01-01", "channel": "search", "target_need": "save_time", "media_spend": "50.00", "other_acquisition_spend": "10.00"},
        {"campaign_id": "JAN", "spend_date": "2024-01-10", "channel": "search", "target_need": "save_time", "media_spend": "50.00", "other_acquisition_spend": "10.00"},
        {"campaign_id": "MAR", "spend_date": "2024-03-01", "channel": "partner", "target_need": "build_skill", "media_spend": "30.00", "other_acquisition_spend": "0.00"},
        {"campaign_id": "EX", "spend_date": "2024-02-01", "channel": "search", "target_need": "save_time", "media_spend": "8.00", "other_acquisition_spend": "0.00"},
    ]
    attrs = []
    for pid, tid, campaign, month in [("A", "TA1", "JAN", 1), ("B", "TB1", "JAN", 1), ("C", "TC3", "MAR", 3), ("X", "TX2", "EX", 2), ("Y", "TY2", "", 2)]:
        attrs.append({"person_id": pid, "first_paid_transaction_id": tid, "credited_campaign_id": campaign,
                      "source_type": "paid_campaign" if campaign else "organic", "attribution_rule": "fixture_rule",
                      "credited_at": f"2024-{month:02d}-04 00:00:00"})
    exps = [{"experiment_id": "TEST", "person_id": pid, "tested_campaign_id": "EX",
             "assigned_at": "2024-02-01 00:00:00", "arm": arm, "followup_end_at": "2024-03-01 00:00:00"}
            for pid, arm in [("X", "treatment"), ("Z", "treatment"), ("Y", "control"), ("W", "control")]]
    all_rows = {"people.csv": people, "subscription_periods.csv": periods, "transactions.csv": transactions,
                "campaign_spend.csv": costs, "acquisition_attribution.csv": attrs,
                "experiment_assignments.csv": exps, "product_events.csv": [], "feedback.csv": []}
    for name, rows in all_rows.items(): _write(d, name, rows)
    _seal(d)
    return d


def test_hand_accounting_and_spend_not_multiplied(hand_data, tmp_path):
    out = tmp_path / "analysis"
    build_views(hand_data, out)
    rows = _read(out / "tables" / "cohort_cash_economics.csv")
    jan = [r for r in rows if r["cohort_month"] == "2024-01-01"]
    assert [float(r["cumulative_contribution"]) for r in jan] == [85, 155, 155]
    assert [float(r["balance_after_acquisition"]) for r in jan] == [-35, 35, 35]
    assert float(jan[0]["cac"]) == 60
    assert jan[0]["first_observed_payback_age"] == "1"
    assert jan[0]["cash_payback_month"] == "2"
    company = _read(out / "tables" / "company_totals.csv")
    assert sum(float(r["acquisition_spend"]) for r in company) == 158
    assert sum(float(r["net_revenue"]) for r in company) == 320
    assert sum(float(r["contribution"]) for r in company) == 206
    january = [r for r in _read(out / "tables" / "cohort_totals.csv") if r["cohort_month"] == "2024-01-01" and r["age_month"] == "0"][0]
    assert january["orders"] == "3"  # two subscriptions + one add-on; refund is not another order.
    assert float(january["gross_payment_revenue"]) == 160
    assert float(january["net_revenue"]) == 140


def test_future_is_missing_and_observed_churn_is_zero(hand_data, tmp_path):
    out = tmp_path / "analysis"
    build_views(hand_data, out)
    rows = _read(out / "tables" / "cohort_age_summary.csv")
    jan = [r for r in rows if r["cohort_month"] == "2024-01-01"]
    mar = [r for r in rows if r["cohort_month"] == "2024-03-01"]
    assert [int(r["n_retained"]) for r in jan] == [2, 1, 0]
    assert [int(r["age_month"]) for r in mar] == [0]
    assert jan[-1]["gross_payment_revenue"] == "0.00"
    assert all(r["calendar_month"] < "2024-04-01" for r in rows)


def test_experiment_keeps_nonbuyers_and_organic_controls(hand_data, tmp_path):
    out = tmp_path / "analysis"
    build_views(hand_data, out)
    rows = _read(out / "tables" / "experiment_summary.csv")
    assert [int(r["n_assigned"]) for r in rows] == [2, 2]
    assert [int(r["n_buyers"]) for r in rows] == [1, 1]
    effect = _read(out / "tables" / "experiment_effects.csv")[0]
    assert float(effect["incremental_buyers"]) == 0
    assert effect["incremental_cac"] == ""  # undefined, not zero or infinity.
    assert float(effect["iroas"]) == 1.25
    assert float(effect["incremental_contribution_after_media"]) == 1
    assert float(effect["incremental_contribution_after_media_per_prospect"]) == 0.5
    organic = [r for r in _read(out / "tables" / "cohort_acquisition_costs.csv") if r["channel"] == "organic"][0]
    assert organic["n_acquired"] == "1" and organic["cac"] == "" and organic["acquisition_spend"] == ""


def test_modified_source_fails_closed(hand_data):
    p = hand_data / "transactions.csv"
    p.write_text(p.read_text(encoding="utf-8").replace("100.00", "101.00", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_data(hand_data)


@pytest.mark.parametrize("problem", ["duplicate", "refund", "prior_buyer", "future", "reactivation", "missing_control"])
def test_semantic_errors_fail_even_with_refreshed_fixture_hashes(hand_data, problem):
    if problem == "duplicate":
        name = "people.csv"; rows = _read(hand_data/name); rows.append(dict(rows[0])); expected = "Duplicate primary"
    elif problem == "refund":
        name = "transactions.csv"; rows = _read(hand_data/name); rows[-1]["refund_amount"] = "200.00"; expected = "Refund exceeds"
    elif problem == "prior_buyer":
        name = "experiment_assignments.csv"; rows = _read(hand_data/name); rows[0]["person_id"] = "A"; expected = "prior buyer"
    elif problem == "future":
        name = "transactions.csv"; rows = _read(hand_data/name); rows[0]["occurred_at"] = "2024-04-03 09:00:00"; expected = "outside observed"
    elif problem == "reactivation":
        name = "subscription_periods.csv"; rows = _read(hand_data/name)
        rows.append({**rows[3], "period_id": "B3", "period_start": "2024-03-03", "period_end": "2024-04-03", "renewal_due_at": "2024-03-03 08:00:00"})
        expected = "reactivation"
    else:
        name = "experiment_assignments.csv"; rows = [r for r in _read(hand_data/name) if r["arm"] == "treatment"]
        expected = "own control"
    _write(hand_data, name, rows); _seal(hand_data)
    with pytest.raises(ValueError, match=expected): validate_data(hand_data)


def test_modified_analysis_fails_closed(hand_data, tmp_path):
    out = tmp_path / "analysis"
    build_views(hand_data, out)
    assert validate_analysis(out)["status"] == "passed"
    p = out / "tables" / "cohort_age_summary.csv"
    p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Analysis table hash mismatch"): validate_analysis(out)


def test_full_refund_does_not_erase_acquisition(hand_data, tmp_path):
    rows = _read(hand_data / "transactions.csv")
    rows[-1]["refund_amount"] = "90.00"  # Entire initial payment after its $10 discount.
    _write(hand_data, "transactions.csv", rows); _seal(hand_data)
    out = tmp_path / "analysis"
    build_views(hand_data, out)
    january = [r for r in _read(out / "tables" / "cohort_totals.csv") if r["cohort_month"] == "2024-01-01" and r["age_month"] == "0"][0]
    assert january["n_acquired"] == "2" and january["n_retained"] == "2"
    assert float(january["gross_payment_revenue"]) == 160
    assert float(january["net_revenue"]) == 70
    assert float(january["contribution"]) == 15


def test_broad_campaign_cost_not_invented_for_segment(hand_data, tmp_path):
    rows = _read(hand_data / "campaign_spend.csv")
    for r in rows:
        if r["campaign_id"] == "JAN": r["target_need"] = ""
    _write(hand_data, "campaign_spend.csv", rows); _seal(hand_data)
    out = tmp_path / "analysis"
    build_views(hand_data, out)
    january = [r for r in _read(out / "tables" / "cohort_acquisition_costs.csv") if r["cohort_month"] == "2024-01-01"][0]
    assert january["cac"] == "" and january["acquisition_spend"] == ""
    company = _read(out / "tables" / "company_totals.csv")
    assert sum(float(r["acquisition_spend"]) for r in company) == 158


def test_canonical_exports_are_seed_reproducible(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    expected = json.loads((repo / "data" / "data_manifest.json").read_text(encoding="utf-8"))
    actual = generate_data(tmp_path / "regenerated", seed=expected["synthetic_seed"])
    assert actual == expected
    assert actual["files"] == expected["files"]
