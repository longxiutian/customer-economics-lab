from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cohort_lab.report_b import incremental_planning
from scripts.verify_reproducibility import command_for

ROOT = Path(__file__).resolve().parents[1]


def test_incremental_recovery_restores_historical_cost_once_and_counts_from_one():
    keys = {"cohort_month": "2025-07-01", "channel": "search", "primary_need": "skill"}
    values = pd.DataFrame([{**keys, "test_id": "one", "horizon_months": 4, "icac": 60.,
                            "ltv_before_cac_mean": 75., "value_less_icac": 15.}])
    cells = pd.DataFrame([{**keys, "cac": 25., "payback_month": 2.}])
    paths = pd.DataFrame([{**keys, "age_month": age, "cash_after_cac_mean": cash}
                         for age, cash in enumerate([-5., 15., 35., 55.])])
    result = incremental_planning(values, cells, paths).iloc[0]
    assert result.historical_payback_receipt == 2
    assert result.planning_payback_receipt == 3
    assert result.break_even_value_share == pytest.approx(.8)
    values.loc[0, "icac"] = 90.
    assert np.isnan(incremental_planning(values, cells, paths).planning_payback_receipt.iloc[0])
    with pytest.raises(ValueError, match="full valuation horizon"):
        incremental_planning(values, cells, paths.iloc[:-1])
    with pytest.raises(ValueError, match="supported historical benchmark"):
        incremental_planning(values, cells.assign(primary_need="different"), paths)


def test_reference_planning_has_seven_and_nine_payment_recovery():
    read = lambda name: pd.read_csv(ROOT / "examples/reference/tables" / name)
    result = incremental_planning(read("channel_value_decision.csv"),
                                  read("strategic_segment_breakout.csv"),
                                  read("segment_forecast_curves.csv")).set_index(["channel", "primary_need"])
    assert result.loc[("partner", "build_skill"), "planning_payback_receipt"] == 7
    assert result.loc[("search", "build_skill"), "planning_payback_receipt"] == 9
    assert result.xs("save_time", level="primary_need").planning_payback_receipt.isna().all()
    assert result.loc[("partner", "build_skill"), "historical_payback_receipt"] == 3
    assert result.loc[("partner", "build_skill"), "break_even_value_share"] == pytest.approx(.5648265)


def test_variant_b_is_explicit_and_default_replay_remains_a(tmp_path):
    kwargs = dict(mode="report", source=tmp_path / "fit", steps=3000, pdf=True)
    assert "--variant" not in command_for(tmp_path / "a", **kwargs)
    command = command_for(tmp_path / "b", variant="B", **kwargs)
    assert command[command.index("--variant") + 1] == "B"
