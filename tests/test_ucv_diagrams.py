"""Protect source meaning, exhaustive UCV coverage and actual native artifacts."""
import csv
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from cohort_lab.data import SCHEMAS, PRIMARY_KEYS
from cohort_lab.diagrams import _erd_candidate, _report_erd_candidate, _knowledge_assets_candidate, _conceptual_journey, build_diagrams
from cohort_lab.ucv import CATEGORIES, CATEGORY_DEFINITIONS, CONTEXT_ONLY_FIELDS, FIELD_GROUPS, build_ucv_tables, ucv_markdown


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    folder=tmp_path_factory.mktemp("ucv")
    shutil.copytree(Path(__file__).resolve().parents[1]/'data',folder,dirs_exist_ok=True)
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
    assert set(CATEGORY_DEFINITIONS)==set(CATEGORIES)
    assert "Firm marketing activity" in CATEGORY_DEFINITIONS["Engagement"]
    assert "do not establish individual exposure" in CATEGORY_DEFINITIONS["Engagement"]
    for table in tables:
        assert table["context_only_fields"]==CONTEXT_ONLY_FIELDS[table["file"]]
        for field in table["context_only_fields"]:
            assert field in table["rationale"] and table["rationale"][field].strip()
            assert f"`{field}`†" in text
            assert f"`{field}†`" not in text
    assert "Channel describes the firm's marketing activity" in by_name["campaign_spend.csv"]["rationale"]["target_need"]
    assert "realized amounts record transaction Engagement" in by_name["transactions.csv"]["rationale"]["unit_price"]


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
    assert ucv["category_definitions"]==CATEGORY_DEFINITIONS
    for stem in ("source-systems","source-tables","source-tables-report","source-systems-report","knowledge-assets","journey-save-time","journey-build-skill"):
        info=first["diagrams"][stem]
        assert (one/info["png"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        svg=(one/info["svg"]).read_text(encoding="utf-8")
        assert '<svg' in svg and 'data-quality-profile="standard"' in svg
        assert '<script' not in svg
        assert 'data-legend-bridge-runtime' not in svg
    svg=(one/"diagrams/source-tables.svg").read_text(encoding="utf-8")
    assert "related_transaction_id" in svg and "campaign_metadata" in svg
    report_svg=(one/"diagrams/source-systems-report.svg").read_text(encoding="utf-8")
    assert "font-size: 12px" in report_svg
    assert "Company direction and next action</text>" not in report_svg
    assert "person_id / period_id / campaign_id" in report_svg
    journey_svg=(one/"diagrams/journey-save-time.svg").read_text(encoding="utf-8")
    assert 'font-size: 13px' in journey_svg and 'font-size: 11px' in journey_svg
    assert "people.primary_need" in journey_svg and "renewal_outcome / plan_tier" in journey_svg
    for relative,digest in first["knowledge_asset_hashes"].items():
        assert hashlib.sha256((Path(__file__).resolve().parents[1]/relative).read_bytes()).hexdigest()==digest


def test_knowledge_assets_distinguish_roles_without_distributing_private_generation():
    candidate=_knowledge_assets_candidate()
    by_id={node["id"]:node for node in candidate["components"]}
    assert by_id["article"]["type"]=="external"
    assert by_id["csv"]["type"]=="database"
    assert by_id["student"]["type"]=="frontend"
    assert by_id["model"]["type"]=="backend"
    assert "CPU" in by_id["model"]["label"]
    assert "uv.lock" in by_id["uv"]["label"]
    assert len(candidate["meta"]["legend"]["entries"])==6
    text=json.dumps(candidate)
    assert "generate_data" not in text and "seed" not in text and "DGP" not in text
    assert "Instructor-only future outcomes" in text
    for need in ("save_time","build_skill"):
        journey=_conceptual_journey(need)
        assert len(journey["nodes"])==10
        assert "Hypotheses" in journey["meta"]["subtitle"]
        evidence=[edge for edge in journey["edges"] if edge["id"].startswith("look")]
        assert len(evidence)==5 and all(edge["variant"]=="dashed" for edge in evidence)


def test_local_method_reference_is_a_frozen_licensed_source_notebook():
    folder=Path(__file__).resolve().parents[1]/"assets/articles/orduz-2024-cohort-revenue-retention"
    provenance=json.loads((folder/"provenance.json").read_text(encoding="utf-8"))
    assert provenance["license"]=="MIT" and provenance["executed"] is False
    assert len(provenance["source_commit"])==40
    assert "associated documentation" in (folder/"LICENSE.txt").read_text(encoding="utf-8")
    notebook=json.loads((folder/"source.ipynb").read_text(encoding="utf-8"))
    assert len(notebook["cells"])==provenance["notebook_cells"]
    assert (folder/"orduz-source-notebook.pdf").read_bytes().startswith(b"%PDF-")
    for relative,record in provenance["files"].items():
        payload=(folder/relative).read_bytes()
        assert len(payload)==record["bytes"]
        assert hashlib.sha256(payload).hexdigest()==record["sha256"]
