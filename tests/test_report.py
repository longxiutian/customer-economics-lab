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
    assert set(first["diagrams"])=={"source-systems","customer-journey","journey-save-time","journey-build-skill"}
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
