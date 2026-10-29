"""Protect source meaning, exhaustive UCV coverage and actual native artifacts."""
import csv
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from cohort_lab.data import SCHEMAS, PRIMARY_KEYS, generate_data
from cohort_lab.diagrams import _erd_candidate, _report_erd_candidate, build_diagrams
from cohort_lab.ucv import CATEGORIES, FIELD_GROUPS, build_ucv_tables, ucv_markdown


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    folder=tmp_path_factory.mktemp("ucv")
    generate_data(folder)
    return folder


def test_ucv_classifies_every_actual_field_once_and_preserves_evidence_gaps(sources):
    tables=build_ucv_tables(sources)
    assert len(tables)==len(SCHEMAS)==8
    for table in tables:
        assert tuple(table["columns"])==CATEGORIES
        names=[name for fields in table["columns"].values() for name in fields]
        assert len(names)==len(set(names))
        assert set(names)==set(SCHEMAS[table["file"]])
        assert table["source_sha256"]==hashlib.sha256((sources/table["file"]).read_bytes()).hexdigest()
    by_name={table["file"]:table for table in tables}
    assert by_name["people.csv"]["columns"]["Perception"]==["primary_need"]
    assert not by_name["campaign_spend.csv"]["columns"]["Perception"]
    assert "not individual" in by_name["campaign_spend.csv"]["rationale"]["media_spend"]
    assert "not a customer action" in by_name["acquisition_attribution.csv"]["rationale"]["attribution_rule"]
    text=ucv_markdown(tables)
    assert "Universal Customer View" in text and "Unified Customer View" not in text
    assert text.count("| Identifiers | Engagement | Relationship | Perception |")==8


def test_ucv_refuses_schema_drift_and_duplicate_classification(sources,tmp_path,monkeypatch):
    copy=tmp_path/"sources";shutil.copytree(sources,copy)
    people=copy/"people.csv"
    text=people.read_text(encoding="utf-8");people.write_text(text.replace("primary_need","inferred_need",1),encoding="utf-8")
    with pytest.raises(ValueError,match="schema mismatch"):
        build_ucv_tables(copy)
    changed={k:list(v) for k,v in FIELD_GROUPS["people.csv"].items()}
    changed["Engagement"]=["primary_need"]
    monkeypatch.setitem(FIELD_GROUPS,"people.csv",changed)
    with pytest.raises(ValueError,match="exactly once"):
        build_ucv_tables(sources)


def test_erd_retains_every_column_and_uses_a_unique_campaign_parent():
    erd=_erd_candidate();entities={e["id"]:e for e in erd["entities"]}
    assert set(entities)=={name.removesuffix(".csv") for name in SCHEMAS}|{"campaign_metadata"}
    for filename,schema in SCHEMAS.items():
        name=filename.removesuffix(".csv");attrs=entities[name]["attributes"]
        assert {a["name"]:a["type"] for a in attrs}==schema
        assert {a["name"] for a in attrs if "pk" in ([a.get("key")] if isinstance(a.get("key"),str) else a.get("key",[]))}==set(PRIMARY_KEYS[filename])
    for entity in entities.values():
        for attr in entity["attributes"]:
            if "references" in attr:
                parent,field=attr["references"].split(".")
                assert field in {a["name"] for a in entities[parent]["attributes"]}
    spend={a["name"]:a for a in entities["campaign_spend"]["attributes"]}
    assert spend["campaign_id"]["key"]==["pk","fk"]
    assert spend["campaign_id"]["references"]=="campaign_metadata.campaign_id"
    assert "not a ninth source" in entities["campaign_metadata"]["sublabel"]
    tested={a["name"]:a for a in entities["experiment_assignments"]["attributes"]}
    assert tested["tested_campaign_id"]["references"]=="campaign_metadata.campaign_id"
    test_link=next(r for r in erd["relationships"] if r["from"]=="experiment_assignments" and r["to"]=="campaign_metadata")
    assert "campaign_metadata" in test_link["label"]
    assert "transactions.related_transaction_id → transactions.transaction_id" in json.dumps(erd["cards"],ensure_ascii=False)
    compact=_report_erd_candidate()
    assert compact["relationships"]==erd["relationships"]
    for full,print_entity in zip(erd["entities"],compact["entities"]):
        assert [{k:v for k,v in a.items() if k!="type"} for a in full["attributes"]]==print_entity["attributes"]


@pytest.mark.skipif(not shutil.which("node"),reason="Native Archify requires Node")
def test_native_assets_and_ucv_manifest_are_reproducible(sources,tmp_path):
    one=tmp_path/"one";two=tmp_path/"two"
    first=build_diagrams(sources,one);second=build_diagrams(sources,two)
    assert first["output_hashes"]==second["output_hashes"]
    for relative,digest in first["output_hashes"].items():
        assert hashlib.sha256((one/relative).read_bytes()).hexdigest()==digest
    ucv=json.loads((one/first["ucv"]["json"]).read_text(encoding="utf-8"))
    assert ucv["framework"]=="Universal Customer View"
    assert len(ucv["tables"])==8
    for stem in ("source-systems","source-tables","source-tables-report","source-systems-report"):
        info=first["diagrams"][stem]
        assert (one/info["png"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        svg=(one/info["svg"]).read_text(encoding="utf-8")
        assert '<svg' in svg and 'data-quality-profile="standard"' in svg
        assert '<script' not in svg
    svg=(one/"diagrams/source-tables.svg").read_text(encoding="utf-8")
    assert "related_transaction_id" in svg and "campaign_metadata" in svg
    report_svg=(one/"diagrams/source-systems-report.svg").read_text(encoding="utf-8")
    assert "font-size: 12px" in report_svg
    assert "Company direction and next action</text>" not in report_svg
    assert "person_id / period_id / campaign_id" in report_svg
