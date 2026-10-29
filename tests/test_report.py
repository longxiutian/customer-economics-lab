"""Reporting checks protect units, missing observations and provenance."""
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from cohort_lab.analysis import build_views
from cohort_lab.data import generate_data
from cohort_lab import report
from cohort_lab.diagrams import build_diagrams, _conceptual_journey


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    root=tmp_path_factory.mktemp("report-evidence")
    data=root/"data";output=root/"outputs"
    generate_data(data);build_views(data,output)
    return data,output


def test_charts_preserve_age_zero_missing_future_and_money_units(evidence,monkeypatch):
    _,output=evidence
    saved={}
    actual_save=report._save
    def capture(fig,directory,name):
        if name=="cohort-triangles":
            saved["retention"]=np.ma.asarray(fig.axes[0].images[0].get_array()).copy()
            saved["cash"]=np.ma.asarray(fig.axes[1].images[0].get_array()).copy()
        if name=="channel-segment-retention":
            saved["facets"]=[[(line.get_xdata().copy(),line.get_ydata().copy()) for line in ax.lines] for ax in fig.axes]
        return actual_save(fig,directory,name)
    monkeypatch.setattr(report,"_save",capture)
    manifest=report.build_charts(output)
    assert len(manifest["figures"])==6
    experiment=manifest["figures"]["experiment-effects"]["display_values"]
    effects=pd.read_csv(output/"tables/experiment_effects.csv")
    np.testing.assert_allclose(experiment["ci_lower"],effects.incremental_contribution_after_media_per_prospect_ci_lower)
    np.testing.assert_allclose(experiment["ci_upper"],effects.incremental_contribution_after_media_per_prospect_ci_upper)
    assert experiment["followup_days"]==[31,30]
    assert all(lo<0<hi for lo,hi in zip(experiment["ci_lower"],experiment["ci_upper"]))
    assert manifest["figures"]["cohort-triangles"]["display_values"]["age_months"]==list(range(12))
    # The newest cohort has age0 history, not twelve zeros or twelve forecasts.
    assert saved["retention"][-1,0]==1
    assert saved["retention"].mask[-1,1:].all()
    cohorts=manifest["figures"]["cohort-triangles"]["display_values"]["cohorts"]
    cash=pd.read_csv(output/"tables/cohort_cash_economics.csv")
    for row,cohort in enumerate(cohorts):
        for _,r in cash[cash.cohort_month==cohort].iterrows():
            if r.age_month<12:
                assert saved["cash"][row,int(r.age_month)]==pytest.approx(r.balance_per_customer)
    # Every plotted source is bound to the existing saved SQL output bytes.
    for filename,digest in manifest["sources"].items():
        assert hashlib.sha256((output/"tables"/filename).read_bytes()).hexdigest()==digest
    cells=pd.read_csv(output/"tables/cohort_age_summary.csv")
    assert len(saved["facets"])==4
    for panel,(channel,need) in zip(saved["facets"],[("search","save_time"),("search","build_skill"),("partner","save_time"),("partner","build_skill")]):
        for (x,y),cohort in zip(panel,["2024-01-01","2025-01-01","2025-07-01"]):
            rows=cells[(cells.channel==channel)&(cells.primary_need==need)&(cells.cohort_month==cohort)&(cells.age_month<=11)].sort_values("age_month")
            np.testing.assert_array_equal(x,rows.age_month)
            np.testing.assert_allclose(y,rows.n_retained/rows.n_acquired)
        assert panel[-1][0].max()==5  # No invented future for the July2025 cohort.


def test_changed_table_is_rejected_before_plotting(evidence,tmp_path):
    _,source=evidence;output=tmp_path/"changed"
    shutil.copytree(source,output)
    p=output/"tables/company_totals.csv";p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError,match="hash|changed|mismatch"):
        report.build_charts(output)


def test_duplicate_grain_cannot_be_hidden_by_plotting():
    df=pd.DataFrame({"cohort_month":["2024-01","2024-01"],"age_month":[0,0]})
    with pytest.raises(ValueError,match="grain error"):
        report._validate_unique(df,["cohort_month","age_month"],"fixture")


def test_report_escapes_learner_text():
    assert report._tex("Gain 5% & $20_{net} \\input{secret}")==r"Gain 5\% \& \$20\_\{net\} \textbackslash{}input\{secret\}"


def test_model_manifest_must_bind_every_output(tmp_path):
    (tmp_path/"model_manifest.json").write_text(json.dumps({"output_hashes":{}}),encoding="utf-8")
    with pytest.raises(ValueError,match="Unexpected model output"):
        report._validate_model_outputs(tmp_path)


def test_report_uses_the_pinned_portable_maintained_style():
    manifest = report._validate_style()
    assert manifest["upstream_skill"] == "build-longxiu-research-briefs"
    assert manifest["upstream_style_version"] == "2026-08-22-v1.1"
    assert manifest["paper_size_points"] == [612, 792]
    assert manifest["required_typeface"] == "Source Sans"
    wrapper = (report.ROOT / "templates/labreport.sty").read_text()
    assert r"\RequirePackage{longxiu-research-brief}" in wrapper
    skill = (report.ROOT / manifest["supporting_skill"]).read_text()
    assert "Every modeling report must include a technical appendix" in skill
    assert "One table **per raw dataset**" in skill
    assert "before displaying forecast curves" in skill
    assert "private skill" in skill
    # Public instructions and TeX have no author-machine path requirement.
    for path in [report.ROOT / manifest["supporting_skill"],
                 report.ROOT / "docs/report-format-provenance.md",
                 report.ROOT / "templates/labreport.sty"]:
        text = path.read_text()
        assert "C:\\Users\\" not in text and "/Users/" not in text


def test_a_changed_upstream_style_is_not_silently_accepted(tmp_path, monkeypatch):
    root = tmp_path / "isolated-repo"
    shutil.copytree(report.ROOT / "templates", root / "templates")
    upstream = root / "templates/longxiu-research-brief.sty"
    upstream.write_bytes(upstream.read_bytes() + b"\n% changed\n")
    monkeypatch.setattr(report, "ROOT", root)
    with pytest.raises(ValueError, match="style hash mismatch"):
        report._validate_style()


def test_conceptual_journeys_are_segment_specific_hypotheses():
    time=_conceptual_journey("save_time");skill=_conceptual_journey("build_skill")
    assert "Hypotheses" in time["meta"]["subtitle"]
    assert time["nodes"][0]["label"]!=skill["nodes"][0]["label"]
    assert time["nodes"][0]["label"]=="Recognize friction"
    assert skill["nodes"][0]["label"]=="Set a learning goal"
    assert any("not proof" in x for card in time["cards"] for x in card["items"])


@pytest.mark.skipif(not shutil.which("node"),reason="Native Archify renderer requires Node")
def test_native_archify_is_reproducible_and_observed_timeline_keeps_provenance(evidence,tmp_path):
    data,_=evidence
    first=build_diagrams(data,tmp_path/"one");second=build_diagrams(data,tmp_path/"two")
    assert set(first["diagrams"])=={"source-systems","source-systems-report","source-tables","source-tables-report","customer-journey","journey-save-time","journey-build-skill"}
    assert len(first["sources"])==8
    assert {k:v["sha256"] for k,v in first["diagrams"].items()}=={k:v["sha256"] for k,v in second["diagrams"].items()}
    timeline=json.loads((tmp_path/"one/diagrams/customer-journey.json").read_text())
    assert timeline["meta"]["evidence"]=="observed"
    assert len(timeline["events"])>0
    statements=(tmp_path/"one/diagrams/inspection.sql").read_text()
    assert "first_paid" in statements and "INTERVAL '30 days'" in statements
    # Changed source bytes are refused rather than redrawn under stale hashes.
    altered=tmp_path/"altered-data";shutil.copytree(data,altered)
    p=altered/"people.csv";p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError,match="hash|changed|mismatch"):
        build_diagrams(altered,tmp_path/"bad-diagram")


def test_ucv_report_preserves_four_categories_and_explicit_missingness():
    source = {"file": "example.csv", "source": "CRM", "grain": "one row per person",
              "columns": {"Identifiers": ["person_id"], "Engagement": [],
                          "Relationship": ["joined_at"], "Perception": ["stated_need"]}}
    table = report._ucv_table(source)
    assert all(r"\textbf{" + name + "}" in table for name in source["columns"])
    assert "Not observed" in table
    assert "example.csv" in table
    assert table.count(r"person\_\allowbreak{}id") == 1
    del source["columns"]["Perception"]
    with pytest.raises(ValueError, match="all four"):
        report._ucv_table(source)


def test_executive_template_has_business_model_and_required_appendices():
    template = (report.ROOT / "templates/customer-economics-report.tex.j2").read_text()
    assert "Studio North sells a monthly creative-work membership" in template
    assert template.index(r"\VAR{model_description}") < template.index("ltv-and-cac.pdf")
    assert r"\VAR{parameter_table}" in template
    assert r"\VAR{ucv_tables_first}" in template and r"\VAR{ucv_tables_second}" in template
    assert "Management actions and accountability" in template
    for phrase in ("Learner judgment", "Instructor reference build", "In this exercise", "Choose the next action"):
        assert phrase not in template


def test_executive_kpis_are_matched_age_acquisition_value_and_cash(evidence,monkeypatch):
    _,output=evidence
    actual_json=report._json;actual_table=report._table
    def json_input(path):
        if path.name=="model_summary.json":return {"horizon_months":12}
        return actual_json(path)
    def table_input(directory,name,columns=()):
        if name=="cohort_valuation.csv":
            return pd.DataFrame([{"cohort_month":"2025-12-01","net_ltv_mean":100,"net_ltv_p05":90,"net_ltv_p95":110,"forecast_share":.9}])
        return actual_table(directory,name,columns)
    monkeypatch.setattr(report,"_json",json_input);monkeypatch.setattr(report,"_table",table_input)
    context=report._context(output)
    path=report._write_executive_metrics(output,context);kpi=pd.read_csv(path)
    cash=pd.read_csv(output/"tables/cohort_cash_economics.csv")
    expected=cash[cash.age_month==5].sort_values("cohort_month").iloc[[0,-1]]
    monitoring=cash[cash.age_month==5].sort_values("cohort_month").tail(6).balance_per_customer.median()
    assert f"{monitoring:,.2f}" in context["learner_action"]
    assert "not use it as an automatic causal gate" in context["learner_action"]
    assert "extend both campaign follow-ups" in context["learner_action"]
    assert "Renewal is not clearly improving" in context["executive_verdict"]
    assert "2 of 2 intervals include zero" in context["executive_experiment_sentence"]
    assert "dollars squared" in context["segmentation_sentence"]
    assert list(kpi.cohort_month)==list(expected.cohort_month)
    assert (kpi.age_month==5).all()
    np.testing.assert_allclose(kpi.blended_cac,expected.cac,rtol=0,atol=1e-8)
    np.testing.assert_allclose(kpi.cumulative_contribution_per_customer,expected.cumulative_contribution_per_customer,rtol=0,atol=1e-8)
    np.testing.assert_allclose(kpi.cash_after_cac_per_customer,expected.balance_per_customer,rtol=0,atol=1e-8)
    assert kpi.source_sha256.nunique()==1
    assert kpi.source_sha256.iloc[0]==hashlib.sha256((output/"tables/cohort_cash_economics.csv").read_bytes()).hexdigest()
    template=(report.ROOT/"templates/customer-economics-report.tex.j2").read_text()
    for metric in ["acquisition_kpi","value_kpi","cash_kpi"]:assert r"\VAR{"+metric+"}" in template
    assert r"\Metric{Latest observed month}" not in template


def test_payback_validation_excludes_observed_recovery_and_checks_tail_identity():
    frame=pd.DataFrame([
        dict(cohort_month="2024-02-01",observed_months_at_origin=11,horizon_months=12,actual_ltv_before_cac=100,pred_ltv_before_cac=102,baseline_ltv_before_cac=98,actual_forecast_tail_value=10,pred_forecast_tail_value=12,actual_payback_month=6,pred_payback_month=6),
        dict(cohort_month="2024-12-01",observed_months_at_origin=1,horizon_months=12,actual_ltv_before_cac=120,pred_ltv_before_cac=125,baseline_ltv_before_cac=80,actual_forecast_tail_value=100,pred_forecast_tail_value=105,actual_payback_month=4,pred_payback_month=5),
    ])
    summary={"n_forecast_cohorts":2,"n_payback_already_observed":1,"n_both_recovered":1,"payback_mae_months_for_both_recovered":1.,"training_last_calendar_month":"2024-12-01"}
    context=report._valuation_backtest_context(frame.iloc[::-1],summary)
    assert context["valuation_backtest_counts"]=={"rows":2,"already_observed":1,"scored":1,"mae_months":1.}
    assert context["valuation_backtest_table"].index("2024-02")<context["valuation_backtest_table"].index("2024-12")
    assert "Already observed" in context["valuation_backtest_table"] and "Future; scored" in context["valuation_backtest_table"]
    broken=frame.copy();broken.loc[1,"pred_forecast_tail_value"]+=1
    with pytest.raises(ValueError,match="observed prefix"):
        report._valuation_backtest_context(broken,summary)


def test_noncustomer_ucv_rationale_is_printed_from_the_source():
    source={"file":"campaign_spend.csv","source":"Finance","grain":"campaign-date",
            "columns":{"Identifiers":["campaign_id"],"Engagement":["media_spend"],"Relationship":[],"Perception":[]},
            "rationale":{"media_spend":"Firm spending does not establish individual exposure."}}
    assert source["rationale"]["media_spend"] in report._ucv_table(source)
