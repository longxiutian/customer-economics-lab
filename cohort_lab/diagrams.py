"""Archify diagrams generated from the raw CSVs and their actual schemas.

The upstream MIT package is bundled at a pinned public commit. Node is needed,
but students need neither Git nor an account. These are native Archify JSON
diagrams, not a screenshot placed inside a decorative HTML wrapper.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import duckdb
from .data import SCHEMAS, PRIMARY_KEYS, GRAINS
from .ucv import CATEGORY_DEFINITIONS, build_ucv_tables, ucv_markdown

ROOT = Path(__file__).resolve().parent.parent
FILES = ["people.csv", "subscription_periods.csv", "transactions.csv", "product_events.csv",
         "feedback.csv", "campaign_spend.csv", "acquisition_attribution.csv", "experiment_assignments.csv"]
SOURCES = {
    "people.csv": ("CRM", "one person, including nonbuyers"),
    "subscription_periods.csv": ("Renewal system", "one scheduled subscription period"),
    "transactions.csv": ("Finance", "one payment or refund event"),
    "product_events.csv": ("Product", "one observed interaction"),
    "feedback.csv": ("Customer research", "one submitted response"),
    "campaign_spend.csv": ("Marketing", "one campaign-spending date"),
    "acquisition_attribution.csv": ("Marketing", "one acquired person and credited source"),
    "experiment_assignments.csv": ("Experiment platform", "one eligible person per experiment"),
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _sql_path(path):
    return str(Path(path).resolve()).replace("\\", "/").replace("'", "''")


def _raw_views(data_dir):
    con = duckdb.connect()
    statements = []
    for filename in FILES:
        path = Path(data_dir) / filename
        if not path.exists():
            raise FileNotFoundError(f"Expected raw export: {filename}")
        name = filename.removesuffix(".csv")
        sql = f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{_sql_path(path)}', header=true);"
        con.execute(sql); statements.append(sql)
    return con, statements


def _system_candidate(inventory):
    nodes = [
        {"id":"crm","type":"database","label":"CRM profiles","sublabel":"1 row / person_id","stage":0,"row":0},
        {"id":"billing","type":"database","label":"Payments + renewals","sublabel":"transaction / period","stage":0,"row":1},
        {"id":"experience","type":"database","label":"Events + feedback","sublabel":"many / person_id","stage":0,"row":2},
        {"id":"marketing","type":"database","label":"Spend + attribution","sublabel":"campaign / person","stage":0,"row":3},
        {"id":"assignments","type":"database","label":"Random assignment","sublabel":"test × person_id","stage":0,"row":4},
        {"id":"raw","type":"backend","label":"DuckDB SQL","sublabel":"validate → aggregate","stage":1,"row":2,"height":104},
        {"id":"cohorts","type":"database","label":"Saved cohort views","sublabel":"age / segment / cost","stage":2,"row":1},
        {"id":"experiment","type":"database","label":"Saved test views","sublabel":"all assigned people","stage":2,"row":3},
        {"id":"forecast","type":"backend","label":"Forecast + compare","sublabel":"retention → value","stage":3,"row":1},
        {"id":"effects","type":"backend","label":"Estimate test lift","sublabel":"own control window","stage":3,"row":3},
        {"id":"decision","type":"backend","label":"Company direction","sublabel":"LTV / CAC / payback","stage":4,"row":2},
    ]
    edges=[("crm","raw","person_id"),("billing","raw","person / period"),("experience","raw","person_id"),
           ("marketing","raw","campaign_id"),("assignments","raw","all assignments"),
           ("raw","cohorts","customer_month"),("raw","experiment","experiment_person"),
           ("experiment","effects","arm comparison"),("cohorts","forecast","cohort histories"),
           ("effects","decision","tested effects"),("forecast","decision","predicted value")]
    return {"schema_version":1,"diagram_type":"dataflow","meta":{"title":"Studio North: separate records become a company decision","output":"source-systems.html","locale":"en","quality_profile":"standard","animation":"none"},
        "stages":[{"label":"Eight frozen CSV exports"},{"label":"Replay saved SQL"},{"label":"Auditable output tables"},{"label":"Explain uncertainty"},{"label":"Choose and monitor"}],
        "nodes":nodes,"flows":[{"id":f"flow{i}","from":a,"to":b,"label":label} for i,(a,b,label) in enumerate(edges)],
        "cards":[{"dot":"emerald","title":"Same key, different grains","items":[f"{x['file']}: {x['rows']:,} rows; {x['grain']}" for x in inventory[:4]]},
                 {"dot":"orange","title":"The denominator is a business choice","items":[f"{x['file']}: {x['rows']:,} rows; {x['grain']}" for x in inventory[4:]]},
                 {"dot":"cyan","title":"The same business, three kinds of evidence","items":["Observed: customer_month → cohort_age_summary, cohort_cash_economics and company_month. Compare cohorts at the same age.","Forecast: retention and revenue models extend young cohorts, with uncertainty. They do not establish campaign incrementality.","Experimental: experiment_person → experiment_summary → experiment_effects. Keep every assigned person, including nonbuyers.","person_id links one profile to many periods, transactions, events and responses. period_id links one renewal cycle to many financial events.","Aggregate campaign_spend by campaign_id before joining acquisition counts; campaign_id alone is not the raw spend table's primary key."]}]}


def _erd_candidate():
    """All physical columns and honest foreign keys, plus one explicit SQL view."""
    placements = {
        "people": (0, 0, "Customer evidence"), "product_events": (1, 0, "Customer evidence"),
        "feedback": (2, 0, "Customer evidence"),
        "subscription_periods": (0, 1, "Membership economics"), "transactions": (1, 1, "Membership economics"),
        "acquisition_attribution": (0, 2, "Acquisition measurement"), "experiment_assignments": (1, 2, "Acquisition measurement"),
        "campaign_metadata": (0, 3, "Campaign context"), "campaign_spend": (1, 3, "Campaign context"),
    }
    refs = {
        ("subscription_periods", "person_id"): "people.person_id",
        ("transactions", "person_id"): "people.person_id",
        ("transactions", "period_id"): "subscription_periods.period_id",
        ("transactions", "related_transaction_id"): "transactions.transaction_id",
        ("product_events", "person_id"): "people.person_id", ("feedback", "person_id"): "people.person_id",
        ("acquisition_attribution", "person_id"): "people.person_id",
        ("acquisition_attribution", "first_paid_transaction_id"): "transactions.transaction_id",
        ("acquisition_attribution", "credited_campaign_id"): "campaign_metadata.campaign_id",
        ("experiment_assignments", "person_id"): "people.person_id",
        ("experiment_assignments", "tested_campaign_id"): "campaign_metadata.campaign_id",
        ("campaign_spend", "campaign_id"): "campaign_metadata.campaign_id",
    }
    entities = []
    schemas = dict(SCHEMAS)
    schemas["campaign_metadata.csv"] = {"campaign_id": "VARCHAR", "channel": "VARCHAR", "target_need": "VARCHAR"}
    for filename, schema in schemas.items():
        name = filename.removesuffix(".csv"); row, col, tag = placements[name]
        attributes = []
        for field, sql_type in schema.items():
            attr = {"name": field, "type": sql_type}
            keys = []
            if field in PRIMARY_KEYS.get(filename, ["campaign_id"]): keys.append("pk")
            if (name, field) in refs:
                keys.append("fk"); attr["references"] = refs[name, field]
            if keys: attr["key"] = keys[0] if len(keys) == 1 else keys
            attributes.append(attr)
        entities.append({"id": name, "label": name + (" · SQL view" if name == "campaign_metadata" else ""), "tag": tag, "row": row, "col": col,
                         "width": 350, "sublabel": "Derived SQL view; not a ninth source" if name == "campaign_metadata" else "Raw CSV export",
                         "attributes": attributes})
    links = [
        ("subscription_periods", "people", "person_id", "many", False),
        ("transactions", "people", "person_id", "many", False),
        ("transactions", "subscription_periods", "period_id", "many", False),
        ("product_events", "people", "person_id", "many", False),
        ("feedback", "people", "person_id", "many", False),
        ("acquisition_attribution", "people", "person_id", "one", False),
        ("acquisition_attribution", "transactions", "first_paid_transaction_id", "one", False),
        ("acquisition_attribution", "campaign_metadata", "credited_campaign_id", "many", True),
        ("experiment_assignments", "people", "person_id", "many", False),
        ("experiment_assignments", "campaign_metadata", "tested_campaign_id", "many", False),
        ("campaign_spend", "campaign_metadata", "campaign_id", "many", False),
    ]
    relationships = [{"id": f"relation{i}", "from": a, "to": b, "label": label,
                      "fromCardinality": count, "fromOptional": True, "toCardinality": "one", "toOptional": optional}
                     for i, (a, b, label, count, optional) in enumerate(links)]
    # The route runs beside the daily spending table. Name its actual parent so
    # a reader cannot mistake proximity for a join to the nonunique spend key.
    relationships[9]["label"] = "test → campaign_metadata"
    return {"schema_version": 1, "diagram_type": "erd",
            "meta": {"title": "Studio North: source tables, keys and join cardinality", "output": "source-tables.html",
                     "locale": "en", "quality_profile": "standard", "animation": "none",
                     "views": [{"id": "membership", "label": "Membership and cash", "focus": ["people", "subscription_periods", "transactions"], "note": "A person has many scheduled cycles; a cycle can have multiple payments and refunds."},
                               {"id": "experience", "label": "Experience and perceptions", "focus": ["people", "product_events", "feedback"], "note": "Many events or responses may link to one person; missing events do not establish churn."},
                               {"id": "acquisition", "label": "Acquisition and experiments", "focus": ["people", "acquisition_attribution", "experiment_assignments", "campaign_metadata", "campaign_spend"], "note": "Aggregate campaign spending before joining; assignment is not attribution or purchase."}]},
            "layout": {"mode": "grid", "gapX": 65, "gapY": 75, "rowH": 24, "entityW": 350},
            "entities": entities, "relationships": relationships,
            "cards": [{"dot": "cyan", "title": "Every key has a grain", "items": [f"{f.removesuffix('.csv')}: {GRAINS[f]}" for f in FILES[:4]]},
                      {"dot": "emerald", "title": "Campaign IDs are not unique in raw spending", "items": ["campaign_spend has a composite primary key: campaign_id + spend_date. Do not join its daily rows directly to every acquired customer.", "campaign_metadata groups spending by campaign_id and retains its channel and target_need. The source contract verifies that one campaign has one channel and target need.", "A refund's related_transaction_id refers to transactions.transaction_id within the same financial ledger. A payment leaves that optional reference blank."]},
                      {"dot": "orange", "title": "Read the links without changing the denominator", "items": ["Cardinality describes how many child records can reference one parent. A known person can have no purchase, event or feedback.", "acquisition_attribution has at most one row per person; its optional credited_campaign_id is blank for organic credit.", "experiment_assignments has a composite key: experiment_id + person_id. Its tested_campaign_id references campaign_metadata.campaign_id, not campaign_spend. Its people include nonbuyers, who must remain in the analysis.", "Shared IDs make documented joins possible. They do not turn recorded credit into causal evidence or a complete journey."]},
                      {"dot": "cyan", "title": "Refunds reference the same ledger", "items": ["transactions.related_transaction_id → transactions.transaction_id. This optional self-reference links a refund to its original payment. The FK is retained in the table; the native ERD renderer does not draw self-entity edges."]}]}


def _report_system_candidate():
    """A portrait-report overview; full grains and fields live in the linked ERD."""
    nodes = [
        {"id":"experience","lane":"sources","col":0,"type":"database","label":"People + experience","sublabel":"profiles / events / feedback"},
        {"id":"membership","lane":"sources","col":1,"type":"database","label":"Membership + cash","sublabel":"renewals / transactions"},
        {"id":"marketing","lane":"sources","col":2,"type":"database","label":"Marketing + tests","sublabel":"spend / credit / assignment"},
        {"id":"sql","lane":"sql","col":1,"type":"backend","label":"Saved DuckDB SQL views","sublabel":"person_id / period_id / campaign_id","width":220},
        {"id":"observed","lane":"evidence","col":0,"type":"backend","label":"Observed economics","sublabel":"cohorts at the same age"},
        {"id":"forecast","lane":"evidence","col":1,"type":"backend","label":"Retention + revenue","sublabel":"forecast with uncertainty"},
        {"id":"incrementality","lane":"evidence","col":2,"type":"backend","label":"Randomized effects","sublabel":"all assigned; own controls"},
        {"id":"decision","lane":"decision","col":1,"type":"frontend","label":"Are we moving forward?","sublabel":"LTV / CAC / cash payback","width":220},
    ]
    links=[("experience","sql"),("membership","sql"),("marketing","sql"),
           ("sql","observed"),("sql","forecast"),("sql","incrementality"),
           ("observed","decision"),("forecast","decision"),("incrementality","decision")]
    for node in nodes:
        node["width"]=max(node.get("width",0),200)
    return {"schema_version":2,"diagram_type":"workflow",
            "meta":{"title":"Studio North: from separate records to a decision","output":"source-systems-report.html",
                    "locale":"en","quality_profile":"standard","visual_preset":"editorial","animation":"none",
                    "legend":{"entries":{"database":{"label":"Source exports"},"backend":{"label":"Analysis"},"frontend":{"label":"Management decision"}}}},
            "lanes":[{"id":"sources","label":"Eight source exports"},{"id":"sql","label":"Reproducible ETL"},
                     {"id":"evidence","label":"Three complementary forms of evidence"},{"id":"decision","label":"Company direction and next action"}],
            "nodes":nodes,"edges":[{"id":f"report-edge{i}","from":a,"to":b,"fromSide":"bottom","toSide":"top","route":"drop"} for i,(a,b) in enumerate(links)],
            "cards":[{"dot":"cyan","title":"Saved evidence, not a hidden answer","items":["Source files are separate CSV exports with documented keys. DuckDB executes saved SQL locally; no database server is required.","customer_month and cohort_age_summary supply retained customers and revenue; cohort_cash_economics adds acquisition cost and cash recovery.","experiment_person keeps every randomized prospect, including nonbuyers; experiment_effects uses each test's own control and outcome window."]},
                     {"dot":"orange","title":"Read alongside the detailed schema","items":["The source-tables ERD retains every field, key and cardinality; the UCV appendix identifies available and missing kinds of customer evidence.","One person has many periods, transactions, events and responses. Aggregate daily campaign spending before joining acquired customers.","A model forecasts future value; it cannot turn attribution credit or an observed cohort trend into an incremental campaign effect."]}]}


def _report_erd_candidate():
    """Compact print edition: all fields/keys/edges, SQL types in the full ERD."""
    candidate=_erd_candidate()
    candidate["meta"]["title"]="Studio North: all source fields and their connections"
    candidate["meta"]["output"]="source-tables-report.html"
    candidate["layout"].update({"entityW":240,"gapX":35})
    for entity in candidate["entities"]:
        entity["width"]=240
        for attribute in entity["attributes"]:
            attribute.pop("type",None)
    candidate["cards"].append({"dot":"cyan","title":"Print edition","items":["Every source field, primary/foreign key and join is retained. SQL types are listed in the companion full ERD and data dictionary."]})
    return candidate


def _knowledge_assets_candidate() -> dict:
    """Public knowledge/runtime assets; no private generator or holdout enters the map."""
    components = [
        {"id":"article","type":"external","label":"Orduz source notebook","sublabel":"Local PDF + MIT provenance","pos":[40,40],"size":[220,78],"sources":[{"path":"assets/articles/orduz-2024-cohort-revenue-retention/source.ipynb"}]},
        {"id":"student","type":"frontend","label":"Analysis skill","sublabel":"One chat; explicit next stages","pos":[370,40],"size":[220,78],"sources":[{"path":"SKILL.md"}]},
        {"id":"reportskill","type":"frontend","label":"Executive report skill","sublabel":"Narrative + style + appendices","pos":[700,40],"size":[220,78],"sources":[{"path":"skills/executive-report/SKILL.md"}]},
        {"id":"csv","type":"database","label":"Eight frozen CSVs","sublabel":"Schemas + UCV field tables","pos":[40,220],"size":[220,78],"sources":[{"path":"data/data_dictionary.json"},{"path":"cohort_lab/ucv.py"}]},
        {"id":"sql","type":"backend","label":"DuckDB + NumPy/pandas","sublabel":"Saved SQL + checked views","pos":[370,220],"size":[220,78],"sources":[{"path":"cohort_lab/analysis.py"},{"path":"sql/01_views.sql"}]},
        {"id":"model","type":"backend","label":"JAX CPU + NumPyro","sublabel":"Retention + revenue inference","pos":[700,220],"size":[220,78],"sources":[{"path":"cohort_lab/model.py"},{"path":"cohort_lab/benchmark.py"}]},
        {"id":"archify","type":"frontend","label":"Archify skill + Node","sublabel":"Source maps + knowledge assets","pos":[40,400],"size":[220,78],"sources":[{"path":"vendor/archify/SKILL.md"},{"path":"cohort_lab/diagrams.py"}]},
        {"id":"render","type":"backend","label":"Matplotlib + Jinja2","sublabel":"Figures + editable TeX","pos":[370,400],"size":[220,78],"sources":[{"path":"cohort_lab/report.py"},{"path":"templates/customer-economics-report.tex.j2"}]},
        {"id":"output","type":"messagebus","label":"Executive report + evidence","sublabel":"PDF / SQL / model / manifests","pos":[700,400],"size":[220,78],"sources":[{"path":"cohort_lab/report.py"}]},
        {"id":"uv","type":"security","label":"uv + uv.lock","sublabel":"Pinned Python environment","pos":[370,580],"size":[220,78],"sources":[{"path":"pyproject.toml"},{"path":"uv.lock"}]},
    ]
    links = [
        ("article","student","method reference"),("student","reportskill","writing contract"),
        ("student","sql","guides stages"),("reportskill","output","governs report"),
        ("csv","sql","observed rows"),("sql","model","cohort evidence"),
        ("archify","render","native diagrams"),("model","output","forecasts + checks"),
        ("render","output","TeX + figures"),("uv","render","locked packages"),
    ]
    # This is a runtime-generated asset map. Current file hashes belong in the
    # build manifest; a prior Git commit would misdescribe an uncommitted lab.
    for component in components:
        component.pop("sources")
        component["pos"]=[40+(component["pos"][0]-40)/330*265,40+(component["pos"][1]-40)/180*135]
    short_subtitles={"article":"Local PDF + MIT notice","student":"Human review gates","reportskill":"Style + report appendix",
                     "csv":"Schemas + UCV fields","sql":"Saved SQL + checks","model":"Retention + revenue",
                     "render":"Figures + TeX source","output":"PDF, SQL, model, audit","uv":"Locked Python packages"}
    for component in components:
        component["sublabel"]=short_subtitles.get(component["id"],component["sublabel"])
    components[8]["label"]="Executive report"
    return {"schema_version":1,"diagram_type":"architecture",
            "meta":{"title":"Knowledge assets behind the customer-economics framework","output":"knowledge-assets.html",
                    "locale":"en","quality_profile":"standard","animation":"none","visual_preset":"editorial",
                    "legend":{"entries":{"frontend":{"label":"Skills"},"external":{"label":"Reference"},
                        "database":{"label":"Source data"},"backend":{"label":"Computation"},
                        "messagebus":{"label":"Outputs"},"security":{"label":"Environment"}}}},
            "components":components,
            "connections":[{"id":f"knowledge{i}","from":a,"to":b,"label":label,
                            **({"fromSide":"right","toSide":"left","route":"straight"} if i in (0,1,4,5,6,8) else {}),
                            **({"labelAt":[284,25]} if i==0 else {}),
                            **({"labelAt":[549,25]} if i==1 else {}),
                            **({"fromSide":"bottom","toSide":"top","labelAt":[415,145]} if i==2 else {}),
                            **({"label":"","fromSide":"right","toSide":"right","via":[[810,79],[810,349]]} if i==3 else {}),
                            **({"labelAt":[284,160]} if i==4 else {}),
                            **({"labelAt":[549,160]} if i==5 else {}),
                            **({"labelAt":[284,295]} if i==6 else {}),
                            **({"fromSide":"bottom","toSide":"top","labelAt":[680,280]} if i==7 else {}),
                            **({"labelAt":[549,295]} if i==8 else {})}
                           for i,(a,b,label) in enumerate(links)],
            "cards":[{"dot":"cyan","title":"Read the symbols and colors by asset type","items":["Blue skill panels guide the agent; gray reference panels supply methods. Purple database symbols identify frozen evidence; green code symbols identify local computations.","Amber list symbols collect the deliverables. The rose shield identifies the environment pinned through uv.lock. These symbols do not imply a cloud service."]},
                     {"dot":"emerald","title":"The complete runtime is local","items":["Python packages are installed and run with uv. CPU JAX and NumPyro do not require a GPU.","Archify runs with Node; pinned Playwright exports its diagrams. A local TeX engine compiles the report from the bundled style assets.","The learner receives observed source records. Instructor-only future outcomes and data-generation tools are outside this public framework."]}]}


def build_diagrams(data_dir: Path, output_dir: Path) -> dict:
    """Inspect the actual raw exports and render native Archify diagrams."""
    data=Path(data_dir).resolve();output=Path(output_dir).resolve();folder=output/"diagrams";folder.mkdir(parents=True,exist_ok=True)
    from .data import validate_data
    validate_data(data)
    node=shutil.which("node")
    if not node:raise RuntimeError("Archify requires Node.js18 or later on PATH; no Git/account is required")
    vendor=ROOT/"vendor/archify"
    if not (vendor/"LICENSE").exists():raise RuntimeError("Pinned Archify package or MIT license is missing")
    con,sql_log=_raw_views(data)
    inventory=[]
    for file in FILES:
        name=file.removesuffix(".csv");count_sql=f"SELECT count(*) FROM {name}";sql_log.append(count_sql)
        inventory.append({"file":file,"rows":con.execute(count_sql).fetchone()[0],"source":SOURCES[file][0],"grain":SOURCES[file][1],"sha256":_sha(data/file)})
    candidates={"source-systems":_system_candidate(inventory),"source-tables":_erd_candidate(),"source-tables-report":_report_erd_candidate(),"source-systems-report":_report_system_candidate(),"knowledge-assets":_knowledge_assets_candidate()}
    con.close()
    (folder/"inspection.sql").write_text(";\n\n".join(s.rstrip(';') for s in sql_log)+";\n",encoding="utf-8")
    _write(folder/"source_inventory.json",inventory)
    ucv_tables=build_ucv_tables(data)
    _write(folder/"ucv-tables.json",{"framework":"Universal Customer View","categories":["Identifiers","Engagement","Relationship","Perception"],"category_definitions":CATEGORY_DEFINITIONS,"tables":ucv_tables})
    (folder/"ucv-tables.md").write_text(ucv_markdown(ucv_tables),encoding="utf-8")
    from .business_journey import build_business_journey
    results={"business-journey":build_business_journey(folder)}
    for stem,candidate in candidates.items():
        source=folder/f"{stem}.json";dest=folder/f"{stem}.html";_write(source,candidate)
        kind=candidate["diagram_type"]
        renderer=vendor/"renderers"/kind/f"render-{kind}.mjs"
        p=subprocess.run([node,str(renderer),str(source),str(dest)],cwd=folder,text=True,capture_output=True,timeout=120)
        (folder/f"{stem}.render.log").write_text(p.stdout+p.stderr,encoding="utf-8")
        if p.returncode or not dest.exists():raise RuntimeError(f"Archify {kind} render failed: "+(p.stdout+p.stderr)[-3500:])
        results[stem]={"json":f"diagrams/{source.name}","html":f"diagrams/{dest.name}","sha256":_sha(dest),"renderer":"native Archify "+kind}
    # The report includes the real native overview. Missing browser support is
    # an explicit failure; an old reference PNG is never silently substituted.
    static_stems=("source-systems","source-tables","source-tables-report","source-systems-report",
                  "knowledge-assets","business-journey")
    p=subprocess.run([node,str(ROOT/"scripts/export_diagram_assets.mjs"),
                      *[str(folder/f"{stem}.html") for stem in static_stems]],
                     cwd=ROOT,text=True,capture_output=True,timeout=120)
    (folder/"static-assets.render.log").write_text(p.stdout+p.stderr,encoding="utf-8")
    if p.returncode:
        raise RuntimeError("Native Archify static export failed: "+(p.stdout+p.stderr)[-3500:])
    for stem in static_stems:
        for suffix in ("svg","png"):
            asset=folder/f"{stem}.{suffix}"
            if not asset.is_file(): raise RuntimeError(f"Native Archify static export missing: {asset.name}")
            results[stem][suffix]=f"diagrams/{asset.name}"
    outputs=[folder/"ucv-tables.json",folder/"ucv-tables.md",folder/"source_inventory.json"]
    outputs.extend(folder/Path(info[field]).name for info in results.values() for field in ("json","html","svg","png") if field in info)
    knowledge_paths=("SKILL.md","skills/executive-report/SKILL.md","assets/articles/orduz-2024-cohort-revenue-retention/orduz-source-notebook.pdf",
                     "assets/articles/orduz-2024-cohort-revenue-retention/LICENSE.txt","cohort_lab/ucv.py","cohort_lab/analysis.py",
                     "cohort_lab/model.py","cohort_lab/benchmark.py","cohort_lab/diagrams.py","cohort_lab/business_journey.py","cohort_lab/report.py",
                     "vendor/archify/SKILL.md","templates/customer-economics-report.tex.j2","pyproject.toml","uv.lock")
    result={"archify":_json_provenance(),"sources":inventory,"diagrams":results,
            "knowledge_asset_hashes":{relative:_sha(ROOT/relative) for relative in knowledge_paths},
            "static_renderer":{"package":"playwright","version":"1.62.1","script_sha256":_sha(ROOT/"scripts/export_diagram_assets.mjs"),"viewport":[2400,1600],"device_scale_factor":2,"theme":"light","animations":"disabled","locale":"en-US","timezone":"UTC","interactive_ui":"Runtime legend hitboxes/count badges omitted; authored semantic labels and swatches preserved","report_overview":"Native nodes and edges; reader swimlanes/legend omitted; 12px titles and 9px context; cropped with 20px margin","business_journey":"One original qualitative experience-map SVG; possible benefits and friction, no measured sentiment","knowledge_assets":"Compact native architecture with type colors and glyphs; 14px titles and 13px context"},
            "ucv":{"json":"diagrams/ucv-tables.json","markdown":"diagrams/ucv-tables.md"},
            "output_hashes":{p.relative_to(output).as_posix():_sha(p) for p in outputs},
            "verification":"Native renderer validation passed; browser and visual review are separate development checks."}
    _write(folder/"diagram_manifest.json",result)
    return result


def _json_provenance():
    return json.loads((ROOT/"vendor/archify-provenance.json").read_text(encoding="utf-8"))
