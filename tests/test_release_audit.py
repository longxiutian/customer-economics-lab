"""Independent release-audit checks: real stage gates and unequal-arm arithmetic."""
from pathlib import Path
import hashlib
import csv
import json
import shutil
import subprocess
import sys

import duckdb
import numpy as np
import pandas as pd
import pytest

from cohort_lab.workflow import LabWorkflow

ROOT = Path(__file__).resolve().parents[1]


def test_independent_real_guided_forward_walk_stops_on_questions(tmp_path):
    """Follow the public skill through real stages, without a mocked stage runner."""
    if not shutil.which("node"):
        pytest.skip("Archify forward smoke requires documented Node prerequisite")
    out = tmp_path / "student"
    lab = LabWorkflow(ROOT / "data", out, compile_pdf=False)
    initial = lab.start()
    assert initial["stage"] == 0 and initial["advanced"]
    assert not (out / "tables").exists()
    question = lab.handle_message("What does a first-paid cohort mean?")
    assert not question["advanced"] and question["state"]["completed_stage"] == 0
    assert lab.handle_message("next")["stage"] == 1
    assert (out / "diagrams" / "source-systems.html").is_file()
    assert not (out / "tables").exists()
    assert lab.handle_message("next")["stage"] == 2
    assert not lab.handle_message("Can we group by need instead of age?")["advanced"]
    lab.set_choice("segmentation_rationale", "Need may describe the job customers want done; check it on mature cohorts.")
    resumed = LabWorkflow(ROOT / "data", out, compile_pdf=False)
    state = resumed.start()["state"]
    assert state["completed_stage"] == 2
    assert state["choices"]["segmentation_rationale"].startswith("Need may")
    assert resumed.handle_message("next")["stage"] == 3
    assert (out / "tables" / "cohort_age_summary.csv").is_file()
    assert not (out / "model_summary.json").exists()
    assert not (out / "report" / "customer-economics-report.pdf").exists()
    assert resumed.status()["state"]["completed_stage"] == 3
    manifest = json.loads((ROOT / "data" / "data_manifest.json").read_text())
    assert all(hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest() == spec["sha256"]
               for name, spec in manifest["files"].items())



def test_stage5_rejects_tampered_experiment_outputs(tmp_path):
    from cohort_lab.workflow import execute_stage
    from cohort_lab.analysis import build_views
    build_views(ROOT / "data", tmp_path)
    summary = tmp_path / "tables" / "experiment_summary.csv"
    summary.write_text(summary.read_text().replace("250", "999", 1))
    with pytest.raises(ValueError, match="hash mismatch"):
        execute_stage(5, ROOT / "data", tmp_path, {}, compile_pdf=False)


def test_experiment_effects_scale_unequal_assignment_arms():
    """A 4-person treatment must compare with twice the 2-person control totals."""
    sql = (ROOT / "sql" / "01_views.sql").read_text()
    effect_sql = sql.split("CREATE OR REPLACE VIEW experiment_effects AS", 1)[1].split("CREATE OR REPLACE VIEW segmentation_comparison AS", 1)[0]
    con = duckdb.connect()
    try:
        con.execute("""CREATE TABLE experiment_summary AS SELECT * FROM (VALUES
          ('X','search','save_time','treatment',4,3,60.0,24.0,10.0,TIMESTAMP '2025-05-01',TIMESTAMP '2025-06-01',31.0,16.0),
          ('X','search','save_time','control',2,1,12.0,5.0,0.0,TIMESTAMP '2025-05-01',TIMESTAMP '2025-06-01',31.0,12.5))
          t(experiment_id,channel,primary_need,arm,n_assigned,n_buyers,net_revenue,contribution,media_spend,assigned_at,followup_end_at,followup_days,contribution_sample_variance)""")
        con.execute("CREATE VIEW experiment_effects AS" + effect_sql)
        result = con.execute("SELECT incremental_buyers,incremental_net_revenue,incremental_contribution,incremental_contribution_after_media,incremental_contribution_after_media_per_prospect,incremental_cac,iroas FROM experiment_effects").fetchone()
        assert [float(x) for x in result] == pytest.approx([1,36,14,4,1,10,3.6])
        interval=con.execute("SELECT incremental_contribution_after_media_per_prospect_se,incremental_contribution_after_media_per_prospect_ci_lower,incremental_contribution_after_media_per_prospect_ci_upper,followup_days FROM experiment_effects").fetchone()
        # T contributions [0,8,8,8] give s^2=16; C [0,5] gives s^2=12.5.
        se=(16/4+12.5/2)**.5
        assert [float(x) for x in interval] == pytest.approx([se,1-1.96*se,1+1.96*se,31])
    finally:
        con.close()


def test_zip_bootstrap_never_invokes_git(tmp_path, monkeypatch):
    """Even with executable invocation forbidden, source ZIP installation works."""
    import zipfile
    from scripts.bootstrap import install_archive
    def forbidden(*args, **kwargs):
        raise AssertionError("Archive install must not invoke external commands")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in ("SKILL.md", "lab.py", "pyproject.toml"):
            z.write(ROOT / name, "customer-economics-lab-v1/" + name)
    result = install_archive(archive, tmp_path / "downloaded")
    assert (result / "SKILL.md").read_bytes() == (ROOT / "SKILL.md").read_bytes()
    assert not (result / ".git").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Tests Windows native-engine preference over WSL fallback")
def test_native_tex_is_preferred_over_unconfigured_wsl(tmp_path, monkeypatch):
    from cohort_lab import report
    source = tmp_path / "customer-economics-report.tex"
    source.write_text("test source")
    source.with_suffix(".pdf").write_bytes(b"test output, not a rendered report")
    (tmp_path / "labreport.sty").write_text("style")
    calls = []
    monkeypatch.delenv("COHORT_TEX_ENGINE", raising=False)
    monkeypatch.setattr(report.shutil, "which", lambda name: name if name in ("tectonic", "wsl") else None)
    def forbidden_wsl(*args, **kwargs):
        raise AssertionError("A working native TeX installation must not be displaced by an unconfigured WSL")
    monkeypatch.setattr(report.subprocess, "check_output", forbidden_wsl)
    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(report.subprocess, "run", fake_run)
    result = report._compile_native(source)
    assert result["engine"] == "tectonic"
    assert calls and all(command[0] == "tectonic" for command in calls)


def test_report_preserves_the_learners_distinct_judgment(tmp_path, monkeypatch):
    from cohort_lab import report
    (tmp_path / "analysis_summary.json").write_text(json.dumps({"data_as_of": "2026-01-01"}))
    (tmp_path / "model_summary.json").write_text(json.dumps({"horizon_months": 12}))
    (tmp_path / "learner_choices.json").write_text(json.dumps({
        "final_verdict": "Evidence is mixed & not a guarantee.",
        "recommended_action": "Test a $100 offer before expanding."}))
    fixtures = {
        "company_totals.csv": pd.DataFrame([dict(calendar_month="2025-12-01", n_retained=42, net_revenue=1000, contribution=300)]),
        "cohort_valuation.csv": pd.DataFrame([dict(cohort_month="2025-12-01", net_ltv_mean=50, net_ltv_p05=40, net_ltv_p95=60, forecast_share=.8)]),
        "segmentation_comparison.csv": pd.DataFrame([dict(scheme="primary_need", weighted_within_variance=2, n_groups=2, min_group_size=10)]),
        "experiment_effects.csv": pd.DataFrame(),
        "experiment_summary.csv": pd.DataFrame(),
        "cohort_totals.csv": pd.DataFrame([dict(cohort_month=f"{year}-{month:02d}-01",age_month=5,n_acquired=40,n_retained=20 if year==2024 else 28,retained_share=.5 if year==2024 else .7) for year in [2024,2025] for month in range(1,7)]),
        "cohort_cash_economics.csv": pd.DataFrame([dict(cohort_month=f"{year}-{month:02d}-01",age_month=5,n_acquired=40,cac=100 if year==2024 else 80,cumulative_contribution_per_customer=120 if year==2024 else 140,balance_per_customer=20 if year==2024 else 60) for year in [2024,2025] for month in range(1,7)]),
        "cohort_age_summary.csv": pd.DataFrame([dict(cohort_month=f"{year}-{month:02d}-01",channel=channel,primary_need=need,age_month=5,n_acquired=10,n_retained=5 if year==2024 else 7)
            for year in [2024,2025] for month in range(1,7)
            for channel in ['search','partner'] for need in ['save_time','build_skill']]),
        "cohort_economics_ex_tests.csv": pd.DataFrame([dict(cohort_month=f"{year}-{month:02d}-01",age_month=5,n_acquired=40,n_retained=20 if year==2024 else 28,excluded_test_buyers=0,excluded_test_spend=0,acquisition_spend=4000 if year==2024 else 3200,cumulative_contribution=4800 if year==2024 else 5600,balance_after_acquisition=800 if year==2024 else 2400) for year in [2024,2025] for month in range(1,7)]),
    }
    monkeypatch.setattr(report, "_table", lambda output, name: fixtures[name].copy())
    context = report._context(tmp_path)
    assert context["learner_verdict"] == r"Evidence is mixed \& not a guarantee."
    assert context["learner_action"] == r"Test a \$100 offer before expanding."
    template = (ROOT / "templates" / "customer-economics-report.tex.j2").read_text()
    assert r"\VAR{learner_verdict}" in template and r"\VAR{learner_action}" in template


def test_raw_source_as_of_replay_matches_only_history_known_then(tmp_path):
    """Re-export raw systems as of Oct1; their Sep-and-earlier aggregates must agree.

    This rebuilds SQL from dated ledger events and known renewal outcomes, not
    by masking already-aggregated future cells as the model backtest does.
    """
    from cohort_lab.analysis import build_views
    from cohort_lab.data import SCHEMAS
    cutoff = "2025-10-01 00:00:00"
    historic = tmp_path / "historic_sources"
    historic.mkdir()
    fields = {"people.csv":"attributes_recorded_at", "subscription_periods.csv":"renewal_due_at",
              "transactions.csv":"occurred_at", "product_events.csv":"occurred_at",
              "feedback.csv":"submitted_at", "campaign_spend.csv":"spend_date",
              "acquisition_attribution.csv":"credited_at", "experiment_assignments.csv":"assigned_at"}
    manifest = json.loads((ROOT / "data" / "data_manifest.json").read_text())
    manifest.update(dataset_version="audit-as-of", data_as_of="2025-10-01T00:00:00Z")
    manifest["source_cutoffs"] = {name:manifest["data_as_of"] for name in SCHEMAS}
    for name, columns in SCHEMAS.items():
        with (ROOT / "data" / name).open(newline="",encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r[fields[name]] < cutoff[:len(r[fields[name]])]]
        if name == "experiment_assignments.csv":
            rows = [r for r in rows if r["followup_end_at"] <= cutoff]
        path = historic / name
        with path.open("w",newline="",encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(columns),lineterminator="\n")
            writer.writeheader();writer.writerows(rows)
        manifest["files"][name] = {"row_count":len(rows),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    (historic / "data_manifest.json").write_text(json.dumps(manifest,sort_keys=True))
    full, replay = tmp_path / "full", tmp_path / "replay"
    build_views(ROOT / "data",full)
    build_views(historic,replay)
    for name, date_field in (("customer_month","calendar_month"),("cohort_age_summary","calendar_month"),
                             ("company_month","calendar_month"),("cohort_acquisition_costs","cohort_month")):
        complete = pd.read_csv(full/"tables"/(name+".csv"))
        expected = complete[complete[date_field]<"2025-10-01"].reset_index(drop=True)
        actual = pd.read_csv(replay/"tables"/(name+".csv"))
        pd.testing.assert_frame_equal(expected,actual,check_exact=True)
    # Both experiments completed before the cutoff; future purchases must not
    # leak into their prespecified outcomes in either raw-source replay.
    expected = pd.read_csv(full/"tables/experiment_effects.csv")
    actual = pd.read_csv(replay/"tables/experiment_effects.csv")
    uncertainty_columns = [
        "incremental_contribution_after_media_per_prospect_se",
        "incremental_contribution_after_media_per_prospect_ci_lower",
        "incremental_contribution_after_media_per_prospect_ci_upper",
        "incremental_contribution_after_media_se",
        "incremental_contribution_after_media_ci_lower",
        "incremental_contribution_after_media_ci_upper",
    ]
    # Truncating unrelated future source rows can change DuckDB's reduction
    # order for DOUBLE sample variance. Allow only sub-picodollar roundoff in
    # the six variance-derived SE/CI fields; financial points, dates, counts,
    # conversion measures, and every other column must still agree exactly.
    pd.testing.assert_frame_equal(expected.drop(columns=uncertainty_columns),
                                  actual.drop(columns=uncertainty_columns),check_exact=True)
    pd.testing.assert_frame_equal(expected[uncertainty_columns],actual[uncertainty_columns],
                                  check_exact=False,rtol=0,atol=1e-12)


@pytest.fixture
def isolated_model_inputs(tmp_path, monkeypatch):
    """Observed economics only; isolate cost aggregation from optimizer noise."""
    from cohort_lab import model, analysis
    table = tmp_path / "tables"
    table.mkdir()
    frame = pd.DataFrame([dict(cohort_month="2024-01-01",channel="search",primary_need="save_time",
                              cohort_index=0,age_month=age,calendar_month=f"2024-{age+1:02d}-01",
                              n_acquired=10,n_retained=10,gross_payment_revenue=200,net_revenue=200,
                              contribution=100) for age in range(12)])
    frame.to_csv(table/"cohort_age_summary.csv",index=False)
    pd.DataFrame([
        dict(cohort_month="2024-01-01",channel="search",primary_need="save_time",n_acquired=10,acquisition_spend=1000,cac=100),
        dict(cohort_month="2024-01-01",channel="partner",primary_need="build_skill",n_acquired=0,acquisition_spend=300,cac=np.nan),
    ]).to_csv(table/"cohort_acquisition_costs.csv",index=False)
    pd.DataFrame([dict(cohort_month="2024-01-01",age_month=0,n_acquired=10,acquisition_spend=1800)]).to_csv(table/"cohort_cash_economics.csv",index=False)
    monkeypatch.setattr(analysis,"validate_analysis",lambda output:{"status":"test fixture"})
    draws={'mean_beta':np.zeros((model.DRAWS,5)), 'concentration_beta':np.zeros((model.DRAWS,4)),
           'cohort_scale':np.zeros(model.DRAWS), 'cohort_z':np.zeros((model.DRAWS,24)),
           'revenue_beta':np.zeros((model.DRAWS,6)), 'revenue_shape':np.full(model.DRAWS,4.)}
    diagnostic={'max_r_hat':1.,'min_ess':1000.,'divergences':0,'parameter_summary':[],
                'retention_pearson_dispersion':1.,'revenue_pearson_dispersion':1.}
    monkeypatch.setattr(model,"_posterior",lambda *args:(draws,diagnostic))
    monkeypatch.setattr(model,"_backtest",lambda *args:(pd.DataFrame({"fixture":[1]}),{"fixture":True,'diagnostic':diagnostic}))
    monkeypatch.setattr(model,"_valuation_backtest",lambda *args:(pd.DataFrame({"fixture":[1]}),{"fixture":True,'diagnostic':diagnostic}))
    return tmp_path


def test_company_model_includes_zero_conversion_and_unallocated_costs(isolated_model_inputs):
    from cohort_lab import model
    output=isolated_model_inputs
    model.fit_and_forecast(output,steps=3000)
    whole=pd.read_csv(output/"tables/cohort_valuation.csv").iloc[0]
    segment=pd.read_csv(output/"tables/cohort_valuation_by_segment.csv").iloc[0]
    assert whole.acquisition_spend == 1800 #1000 buyer-linked +300 zero-conversion +500 unallocated.
    assert whole.cac == 180 and segment.cac == 100
    assert whole.net_ltv_mean == pytest.approx(segment.net_ltv_mean-80)
    assert whole.payback_status == "not_reached" and segment.payback_status == "observed"
    curve=pd.read_csv(output/"tables/forecast_curve.csv")
    assert curve.cumulative_after_acquisition.iloc[-1] == -600


def test_model_refuses_paid_buyer_cell_without_a_cost_record(isolated_model_inputs):
    from cohort_lab import model
    cost_path=isolated_model_inputs/"tables/cohort_acquisition_costs.csv"
    costs=pd.read_csv(cost_path)
    costs[costs.channel != "search"].to_csv(cost_path,index=False)
    with pytest.raises(ValueError,match="Paid customer cells lack acquisition cost rows"):
        model.fit_and_forecast(isolated_model_inputs,steps=3000)


def test_model_release_gate_rejects_missing_diagnostics(isolated_model_inputs,monkeypatch):
    from cohort_lab import model
    monkeypatch.setattr(model,'_backtest',lambda *args:(pd.DataFrame({'fixture':[1]}),{'diagnostic':{}}))
    with pytest.raises(RuntimeError,match='required diagnostics missing'):
        model.fit_and_forecast(isolated_model_inputs,steps=3000)
