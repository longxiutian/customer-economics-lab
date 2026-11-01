"""Counterexamples for recurring test selection, maturity and input isolation."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from cohort_lab.analysis import build_views
from cohort_lab.data import validate_data
from cohort_lab.decision_metrics import channel_value_decision
from test_data_sql import _read, _write, _seal, hand_data

ROOT = Path(__file__).resolve().parents[1]


def test_newer_unfavorable_test_replaces_older_positive_test(hand_data, tmp_path):
    old = _read(hand_data / "channel_holdouts.csv")
    new = [dict(r, test_id="later-" + r["test_id"], assigned_at="2024-03-01T00:00:00",
                followup_end_at="2024-04-01T00:00:00", n_buyers="0" if r["arm"] == "treatment" else "1")
           for r in old]
    _write(hand_data, "channel_holdouts.csv", old + new); _seal(hand_data)
    out = tmp_path / "latest"
    build_views(hand_data, out)
    history = pd.read_csv(out / "tables/channel_cac.csv")
    current = pd.read_csv(out / "tables/channel_cac_current.csv")
    assert len(history) == 2 * len(current)
    assert current.test_id.str.startswith("later-").all()
    assert current.icac.isna().all()


@pytest.mark.parametrize("start,end,match", [
    ("2024-03-02T00:00:00", "2024-04-02T00:00:00", "incomplete"),
    ("2024-01-01T00:00:00", "2024-02-02T00:00:00", "31-day"),
])
def test_incomplete_or_changed_followup_cannot_enter_current_cost(hand_data, start, end, match):
    rows = [dict(r, assigned_at=start, followup_end_at=end) for r in _read(hand_data / "channel_holdouts.csv")]
    _write(hand_data, "channel_holdouts.csv", rows); _seal(hand_data)
    with pytest.raises(ValueError, match=match):
        validate_data(hand_data)


def test_tied_completion_dates_require_reconciliation(hand_data):
    rows = _read(hand_data / "channel_holdouts.csv")
    _write(hand_data, "channel_holdouts.csv", rows + [dict(r, test_id="duplicate-"+r["test_id"]) for r in rows])
    _seal(hand_data)
    with pytest.raises(ValueError, match="Ambiguous"):
        validate_data(hand_data)


def test_december_cost_uses_latest_complete_mature_value_benchmark():
    costs = pd.DataFrame([dict(test_id="dec", test_month="2025-12-01", channel="search", primary_need="build_skill",
                              incremental_buyers=10, incremental_spend=1000, icac=100)])
    base = dict(channel="search", primary_need="build_skill", n_acquired=50, horizon_months=12,
                forecast_share=.4, ltv_before_cac_mean=300, ltv_before_cac_p05=250, ltv_before_cac_p95=350)
    values = pd.DataFrame([dict(base, cohort_month=month, observed_months=observed)
                           for month, observed in [("2025-06-01",7),("2025-07-01",6),("2025-08-01",5)]])
    result = channel_value_decision(costs, values).iloc[0]
    assert result.test_month == "2025-12-01" and result.cohort_month == "2025-07-01"
    assert result.value_less_icac == 200 and result.planning_net_value == 2000
    values.observed_months = 5
    with pytest.raises(ValueError, match="six observed"):
        channel_value_decision(costs, values)


def test_expansion_preserves_original_july_and_all_operating_files():
    manifest = json.loads((ROOT / "data/data_manifest.json").read_text())
    lineage = manifest["revision_lineage"]
    prefix = (ROOT / "data/channel_holdouts.csv").read_bytes()[:lineage["preserved_holdout_prefix_bytes"]]
    assert hashlib.sha256(prefix).hexdigest() == lineage["previous_holdout_sha256"]
    original = json.loads((ROOT / "examples/reference/analysis_input_manifest.json").read_text())["files"]
    for name in lineage["operational_files_unchanged"]:
        assert hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest() == original[name]["sha256"]
    rows = pd.read_csv(ROOT / "data/channel_holdouts.csv")
    assert len(rows) == 48 and rows.test_id.nunique() == 24
    assert rows.n_assigned.sum() == 24000
    assert (rows.media_spend + rows.other_acquisition_spend).sum() == 264000
