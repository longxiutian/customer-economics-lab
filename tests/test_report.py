"""Reporting checks protect units, missing observations and provenance."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from cohort_lab.analysis import build_views
from cohort_lab import report
from cohort_lab.diagrams import build_diagrams


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    root=tmp_path_factory.mktemp("report-evidence")
    data=root/"data";output=root/"outputs"
    shutil.copytree(Path(__file__).resolve().parents[1]/'data',data);build_views(data,output)
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
            saved["facets"]=[[(line.get_xdata().copy(),line.get_ydata().copy()) for line in ax.lines] for ax in fig.axes[:4]]
        return actual_save(fig,directory,name)
    monkeypatch.setattr(report,"_save",capture)
    manifest=report.build_charts(output)
    assert len(manifest["figures"])==8
    experiment=manifest["figures"]["experiment-effects"]["display_values"]
    effects=pd.read_csv(output/"tables/experiment_effects.csv")
    np.testing.assert_allclose(experiment["ci_lower"],effects.incremental_contribution_after_media_per_prospect_ci_lower)
    np.testing.assert_allclose(experiment["ci_upper"],effects.incremental_contribution_after_media_per_prospect_ci_upper)
    assert experiment["followup_days"]==[31,30]
    assert manifest["figures"]["cohort-triangles"]["display_values"]["age_months"]==list(range(24))
    assert len(manifest["figures"]["cohort-triangles"]["display_values"]["cohorts"])==24
    assert saved["retention"].shape==(24,24)
    assert saved["retention"].count()==sum(range(1,25))
    assert len(manifest["figures"]["retention-and-revenue"]["display_values"]["cohorts"])==24
    # The newest cohort has age0 history, not twelve zeros or twelve forecasts.
    assert saved["retention"][-1,0]==1
    assert saved["retention"].mask[-1,1:].all()
    cohorts=manifest["figures"]["cohort-triangles"]["display_values"]["cohorts"]
    cash=pd.read_csv(output/"tables/cohort_cash_economics.csv")
    for row,cohort in enumerate(cohorts):
        for _,r in cash[cash.cohort_month==cohort].iterrows():
            if r.age_month<24:
                assert saved["cash"][row,int(r.age_month)]==pytest.approx(r.balance_per_customer)
    # Every plotted source is bound to the existing saved SQL output bytes.
    for filename,digest in manifest["sources"].items():
        assert hashlib.sha256((output/"tables"/filename).read_bytes()).hexdigest()==digest
    cells=pd.read_csv(output/"tables/cohort_age_summary.csv")
    assert len(saved["facets"])==4
    for panel,(channel,need) in zip(saved["facets"],[("search","save_time"),("search","build_skill"),("partner","save_time"),("partner","build_skill")]):
        assert len(panel)==24
        for (x,y),cohort in zip(panel,sorted(cells.cohort_month.unique())):
            rows=cells[(cells.channel==channel)&(cells.primary_need==need)&(cells.cohort_month==cohort)].sort_values("age_month")
            np.testing.assert_array_equal(x,rows.age_month)
            np.testing.assert_allclose(y,rows.n_retained/rows.n_acquired)
        assert panel[-1][0].max()==0  # No invented renewal for the newest cohort.
        assert panel[0][0].max()==23


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


def test_business_map_is_one_conceptual_introduction(tmp_path):
    from cohort_lab.business_journey import build_business_journey
    build_business_journey(tmp_path)
    source=json.loads((tmp_path/"business-journey.json").read_text())
    assert source["evidence"]=="conceptual"
    assert len(source["stages"])==6
    assert all(s["potential_benefit"] and s["potential_friction"] for s in source["stages"])
    assert "no score" in source["vertical_position"]
    assert "person_id" not in json.dumps(source)


@pytest.mark.skipif(not shutil.which("node"),reason="Native Archify renderer requires Node")
def test_diagrams_are_reproducible_and_business_map_is_conceptual(evidence,tmp_path):
    data,_=evidence
    first=build_diagrams(data,tmp_path/"one");second=build_diagrams(data,tmp_path/"two")
    assert {"source-systems","source-systems-report","source-tables","source-tables-report","business-journey","knowledge-assets"}.issubset(first["diagrams"])
    assert len(first["sources"])==8
    assert {k:v["sha256"] for k,v in first["diagrams"].items()}=={k:v["sha256"] for k,v in second["diagrams"].items()}
    journey=json.loads((tmp_path/"one/diagrams/business-journey.json").read_text())
    assert journey["evidence"]=="conceptual"
    assert not (tmp_path/"one/diagrams/journey-save-time.html").exists()
    assert not (tmp_path/"one/diagrams/customer-journey.html").exists()
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
    assert table.count(r"\Code{person_id}") == 1
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
            return pd.DataFrame([dict(cohort_month=co,net_ltv_mean=100,net_ltv_p05=90,net_ltv_p95=110,forecast_share=share) for co,share in [('2024-01-01',0),('2025-01-01',0),('2025-12-01',.9)]])
        if name=="valuation_backtest.csv":
            return pd.DataFrame([dict(cohort_month='2024-12-01',observed_months_at_origin=1,pred_ltv_before_cac=120,actual_ltv_before_cac=100)])
        return actual_table(directory,name,columns)
    monkeypatch.setattr(report,"_json",json_input);monkeypatch.setattr(report,"_table",table_input)
    context=report._context(output)
    path=report._write_executive_metrics(output,context);kpi=pd.read_csv(path)
    cash=pd.read_csv(output/"tables/cohort_cash_economics.csv")
    totals=pd.read_csv(output/"tables/cohort_totals.csv")
    windows=[[f"{year}-{month:02d}-01" for month in range(1,7)] for year in [2024,2025]]
    expected=[]
    for months in windows:
        one=cash[(cash.age_month==5)&cash.cohort_month.isin(months)].sort_values("cohort_month")
        weights=one.n_acquired/one.n_acquired.sum()
        expected.append([float((one[col]*weights).sum()) for col in ["cac","cumulative_contribution_per_customer","balance_per_customer"]])
    assert f"{context["renewal_window_evidence"]["experiment_excluded"]["later"]["cash_after_cac_per_customer"]:,.2f}" in context["learner_action"]
    assert "not use it as an automatic causal gate" in context["learner_action"]
    assert "verify that controls stayed protected" in context["learner_action"]
    window=context["renewal_window_evidence"]
    if window["later"]["retained_share"]>window["earlier"]["retained_share"] and window["improved_cells"]==window["total_cells"]:
        assert "Retention also improves within each channel" in context["executive_verdict"]
    assert "intervals include zero" in context["executive_experiment_sentence"]
    assert "dollars squared" in context["segmentation_sentence"]
    assert list(kpi.window_start)==[months[0] for months in windows]
    assert list(kpi.window_end)==[months[-1] for months in windows]
    assert (kpi.age_month==5).all() and (kpi.n_cohorts==6).all()
    np.testing.assert_allclose(kpi[["blended_cac","cumulative_contribution_per_customer","cash_after_cac_per_customer"]],expected,rtol=0,atol=1e-8)
    np.testing.assert_allclose(kpi.cumulative_contribution_per_customer-kpi.blended_cac,kpi.cash_after_cac_per_customer,rtol=0,atol=1e-8)
    audit=json.loads((output/"report/matched_cohort_comparison.json").read_text())
    assert audit["joining_months"]==list(range(1,7))
    assert np.isclose(sum(row["weight"] for row in audit["fixed_paid_mix"]),1.)
    for side,months in zip(["earlier","later"],windows):
        assert audit[side]["cohorts"]==months
        assert np.isclose(sum(audit[side]["cohort_weights"].values()),1.)
        assert np.isclose(audit[side]["paid_fixed_mix_retention"],sum(w["weight"]*cell["retained_share"] for w,cell in zip(audit["fixed_paid_mix"],audit[side]["paid_cells"])))
    assert np.isclose(audit["earlier"]["paid_raw_retention"],audit["earlier"]["paid_fixed_mix_retention"])
    assert kpi.source_sha256.nunique()==1
    assert kpi.source_sha256.iloc[0]==hashlib.sha256((output/"tables/cohort_cash_economics.csv").read_bytes()).hexdigest()
    template=(report.ROOT/"templates/customer-economics-report.tex.j2").read_text()
    for metric in ["acquisition_kpi","value_kpi","cash_kpi"]:assert r"\VAR{"+metric+"}" in template
    assert r"\Metric{Latest observed month}" not in template


def test_fixed_mix_comparison_does_not_mistake_mix_change_for_within_cell_change():
    totals=[];cash=[];cells=[]
    keys=[(c,n) for c in ["search","partner"] for n in ["save_time","build_skill"]]
    for year in [2024,2025]:
        for month in range(1,7):
            cohort=f"{year}-{month:02d}-01";retained=0
            for index,(channel,need) in enumerate(keys):
                high=index<2
                n=(80 if high else 20) if year==2024 else (20 if high else 80)
                kept=int(n*(.9 if high else .1));retained+=kept
                cells.append(dict(cohort_month=cohort,age_month=5,channel=channel,primary_need=need,n_acquired=n,n_retained=kept))
            totals.append(dict(cohort_month=cohort,age_month=5,n_acquired=200,n_retained=retained))
            cash.append(dict(cohort_month=cohort,age_month=5,n_acquired=200,cac=100,cumulative_contribution_per_customer=140,balance_per_customer=40))
    result=report._matched_year_evidence(pd.DataFrame(totals),pd.DataFrame(cash),pd.DataFrame(cells))
    assert result["improved_cells"]==0
    assert result["earlier"]["paid_raw_retention"]==pytest.approx(.74)
    assert result["later"]["paid_raw_retention"]==pytest.approx(.26)
    assert result["later"]["paid_fixed_mix_retention"]==pytest.approx(.74)
    # December or a seventh eligible month must not leak into either season-matched window.
    assert all(len(result[key]["cohorts"])==6 for key in ["earlier","later"])


def test_ex_test_sql_removes_both_arms_and_all_their_later_contribution():
    """An excluded buyer's later receipts must not survive the comparability filter."""
    import duckdb
    sql=(report.ROOT/"sql/01_views.sql").read_text(encoding="utf-8").split("CREATE OR REPLACE VIEW cohort_economics_ex_tests AS",1)[1]
    # This fixture tests the whole-cohort exclusion view; later views have
    # their own field requirements and independent arithmetic fixtures.
    sql=sql.split("\nCREATE OR REPLACE VIEW ",1)[0]
    con=duckdb.connect()
    try:
        con.execute("""CREATE TABLE customer_month AS SELECT person_id,DATE '2025-05-01' cohort_month,16 cohort_index,age_month,
             CAST(DATE '2025-05-01'+age_month*INTERVAL '1 month' AS DATE) calendar_month,1 retained,contribution
             FROM (VALUES ('ordinary',0,10),('ordinary',1,20),('treatment',0,30),('treatment',1,40),('control',0,50),('control',1,60)) t(person_id,age_month,contribution)""")
        con.execute("""CREATE TABLE experiment_assignments AS SELECT * FROM (VALUES
            ('treatment','TEST',TIMESTAMP '2025-05-01',TIMESTAMP '2025-06-01'),
            ('control','TEST',TIMESTAMP '2025-05-01',TIMESTAMP '2025-06-01')) t(person_id,tested_campaign_id,assigned_at,followup_end_at)""")
        con.execute("""CREATE TABLE campaign_spend AS SELECT * FROM (VALUES
            ('TEST',DATE '2025-05-10',5,0),('ORDINARY',DATE '2025-05-10',90,10),
            ('TEST',DATE '2025-07-10',15,0)) t(campaign_id,spend_date,media_spend,other_acquisition_spend)""")
        con.execute("""CREATE TABLE cohort_cash_economics AS SELECT DISTINCT cohort_month,cohort_index,age_month,calendar_month,
             3 n_acquired,105 acquisition_spend FROM customer_month""")
        con.execute("CREATE VIEW cohort_economics_ex_tests AS"+sql)
        actual=con.execute("SELECT n_acquired,n_retained,excluded_test_buyers,excluded_test_spend,acquisition_spend,cumulative_contribution,balance_per_customer FROM cohort_economics_ex_tests ORDER BY age_month").fetchall()
        assert [[float(x) for x in row] for row in actual]==[[1,1,2,5,100,10,-90],[1,1,2,5,100,30,-70]]
    finally:con.close()


def test_native_pdf_commands_and_all_schema_fields_are_copyable(tmp_path):
    from cohort_lab.data import SCHEMAS
    if not any(shutil.which(x) for x in ["pdflatex","tectonic","wsl"]):pytest.skip("Native TeX engine unavailable")
    (tmp_path/"figures").mkdir()
    for name in ["labreport.sty","longxiu-research-brief.sty"]:shutil.copyfile(report.ROOT/"templates"/name,tmp_path/name)
    tokens=["uv sync --frozen","uv run --frozen",*SCHEMAS,*sorted({f for schema in SCHEMAS.values() for f in schema})]
    source=tmp_path/"customer-economics-report.tex"
    source.write_text("\\documentclass{article}\n\\usepackage{labreport}\n\\begin{document}\n"+"\n".join(r"\Code{"+token+r"}\par" for token in tokens)+"\n\\end{document}\n",encoding="utf-8")
    report._compile_native(source)
    assert report._pdf_copyability(source.with_suffix(".pdf"))["status"]=="passed"


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
            "context_only_fields":["media_spend"],
            "rationale":{"media_spend":"Firm spending does not establish individual exposure."}}
    assert source["rationale"]["media_spend"] in report._ucv_table(source)
    assert r"\Code{media_spend}\textsuperscript{\ensuremath{\dagger}}" in report._ucv_table(source)


def test_exhibit_registry_numbers_in_order_and_rejects_ambiguous_references():
    source=(r"See Figure~\ref{fig:curve} and Table~\ref{tab:counts}."
            r"\TableCaption{counts}{Assigned people by arm.}"
            r"\ReportFigure{curve}{Observed customer retention.}{curve.pdf}{3in}"
            r"\FigureCaption{schema}{Source table relationships.}"
            r"\TableCaption{parameters}{Estimated model parameters.}")
    items=report._caption_registry(source)
    assert [(x["type"],x["number"],x["label"]) for x in items]==[
        ("table",1,"tab:counts"),("figure",1,"fig:curve"),
        ("figure",2,"fig:schema"),("table",2,"tab:parameters")]
    with pytest.raises(ValueError,match="Duplicate"):
        report._caption_registry(source+r"\TableCaption{counts}{Repeated.}")
    with pytest.raises(ValueError,match="Unresolved"):
        report._caption_registry(source+r"\ref{fig:missing}")
    with pytest.raises(ValueError,match="descriptive caption"):
        report._caption_registry(r"\TableCaption{empty}{}")


def test_each_ucv_table_has_a_stable_numbered_caption():
    source={"file":"experiment_assignments.csv","source":"Experiments","grain":"assigned person",
            "columns":{"Identifiers":["person_id"],"Engagement":[],"Relationship":["arm"],"Perception":[]}}
    rendered=report._ucv_table(source)
    registry=report._caption_registry(rendered)
    assert registry[0]["label"]=="tab:ucv-experiment-assignments"
    assert "experiment\\_assignments.csv" in registry[0]["caption_tex"]
