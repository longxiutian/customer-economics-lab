"""Independent unequal-arm contribution variance, windows and fixed-cost checks."""
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest


SQL = (Path(__file__).resolve().parents[1]/"sql"/"01_views.sql").read_text()
EXPERIMENT_SQL = "CREATE OR REPLACE VIEW experiment_person AS" + SQL.split(
    "CREATE OR REPLACE VIEW experiment_person AS",1)[1].split(
    "CREATE OR REPLACE VIEW segmentation_subjects AS",1)[0]


def _fixture(start="2025-05-01 00:00:00",end="2025-06-01 00:00:00"):
    """Treatment contributions [8,4,0,0]; control [2,0]; media spend $4."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE experiment_assignments(experiment_id VARCHAR,person_id VARCHAR,tested_campaign_id VARCHAR,arm VARCHAR,assigned_at TIMESTAMP,followup_end_at TIMESTAMP)")
    con.executemany("INSERT INTO experiment_assignments VALUES (?,?,?,?,?,?)",
                    [("X",pid,"C",arm,start,end) for arm,pids in [("treatment",["T1","T2","T3","T4"]),("control",["C1","C2"])] for pid in pids])
    con.execute("CREATE TABLE campaign_metadata AS SELECT 'C' AS campaign_id,'search' AS channel,'save_time' AS target_need")
    con.execute("CREATE TABLE campaign_spend(campaign_id VARCHAR,spend_date DATE,media_spend DECIMAL(18,2))")
    con.execute("INSERT INTO campaign_spend VALUES ('C',?,4.00)",[start[:10]])
    con.execute("CREATE TABLE transactions(person_id VARCHAR,transaction_type VARCHAR,occurred_at TIMESTAMP,gross_amount DECIMAL(18,2),discount_amount DECIMAL(18,2),refund_amount DECIMAL(18,2),variable_cost DECIMAL(18,2))")
    after_start = datetime.fromisoformat(start)+timedelta(hours=1)
    before_start = datetime.fromisoformat(start)-timedelta(seconds=1)
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?)",[
        ("T1","payment",after_start,12,0,0,4),
        ("T2","payment",after_start,8,0,0,4),
        ("C1","payment",after_start,6,0,0,4),
        ("T3","payment",datetime.fromisoformat(end),1000,0,0,0),  # Outside exclusive end.
        ("C2","payment",before_start,1000,0,0,0),                # Before assignment.
    ])
    con.execute(EXPERIMENT_SQL)
    return con


@pytest.mark.parametrize("start,end,days",[
    ("2025-05-01 00:00:00","2025-06-01 00:00:00",31),
    ("2025-09-01 00:00:00","2025-10-01 00:00:00",30),
    ("2025-05-01 12:00:00","2025-05-03 00:00:00",1.5),
])
def test_window_and_unequal_arm_contribution_interval(start,end,days):
    con = _fixture(start,end)
    try:
        summary = con.execute("SELECT arm,n_assigned,n_buyers,contribution,contribution_sample_variance,assigned_at,followup_end_at,followup_days FROM experiment_summary ORDER BY arm").fetchall()
        control,treatment = summary
        assert control[:4] == ("control",2,1,2)
        assert treatment[:4] == ("treatment",4,2,12)
        # Independent hand calculation: T sumsq deviations=44, denominator=3;
        # C sumsq deviations=2, denominator=1. Nonbuyers must be included.
        assert float(control[4]) == pytest.approx(2)
        assert float(treatment[4]) == pytest.approx(44/3)
        assert treatment[5:] == (datetime.fromisoformat(start),datetime.fromisoformat(end),days)
        result = con.execute("SELECT incremental_contribution,incremental_media_spend,incremental_contribution_after_media,incremental_contribution_after_media_per_prospect,incremental_contribution_after_media_per_prospect_se,incremental_contribution_after_media_per_prospect_ci_lower,incremental_contribution_after_media_per_prospect_ci_upper,incremental_contribution_after_media_se,incremental_contribution_after_media_ci_lower,incremental_contribution_after_media_ci_upper,followup_days FROM experiment_effects").fetchone()
        se = (14/3)**.5
        expected = [8,4,4,1,se,1-1.96*se,1+1.96*se,4*se,4-1.96*4*se,4+1.96*4*se,days]
        assert [float(x) for x in result] == pytest.approx(expected)
        people = dict(con.execute("SELECT person_id,contribution FROM experiment_person").fetchall())
        assert people["T3"] == people["T4"] == people["C2"] == 0
    finally:
        con.close()


def test_fixed_media_spending_changes_mean_but_not_sampling_standard_error():
    con = _fixture()
    try:
        query = "SELECT incremental_contribution_after_media_per_prospect,incremental_contribution_after_media_per_prospect_se,incremental_contribution_after_media_per_prospect_ci_upper-incremental_contribution_after_media_per_prospect_ci_lower FROM experiment_effects"
        before = con.execute(query).fetchone()
        con.execute("UPDATE campaign_spend SET media_spend=40")
        after = con.execute(query).fetchone()
        assert float(after[0])-float(before[0]) == pytest.approx(-9)
        assert after[1:] == pytest.approx(before[1:])
    finally:
        con.close()


def test_insufficient_arm_size_gives_missing_uncertainty_not_false_precision():
    con = _fixture()
    try:
        con.execute("DELETE FROM experiment_assignments WHERE person_id NOT IN ('T1','C1')")
        result = con.execute("SELECT incremental_contribution_after_media_per_prospect_se,incremental_contribution_after_media_per_prospect_ci_lower,incremental_contribution_after_media_per_prospect_ci_upper FROM experiment_effects").fetchone()
        assert result == (None,None,None)
    finally:
        con.close()
