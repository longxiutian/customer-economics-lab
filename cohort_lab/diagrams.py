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
from .ucv import build_ucv_tables, ucv_markdown

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


def _journey_candidate(con, sql_log):
    choose="""SELECT p.person_id FROM people p
        JOIN feedback f USING(person_id)
        JOIN transactions t USING(person_id)
        WHERE t.transaction_type='payment'
        GROUP BY p.person_id ORDER BY min(t.occurred_at), p.person_id LIMIT 1"""
    sql_log.append(choose); row=con.execute(choose).fetchone()
    if not row:
        raise ValueError("A recorded journey needs at least one linked customer with payment and feedback")
    person=str(row[0]); literal=person.replace("'","''")
    query=f"""WITH first_paid AS (
      SELECT min(occurred_at::TIMESTAMP) AS first_paid_at FROM transactions
      WHERE person_id='{literal}' AND transaction_type='payment'),
    observations AS (
      SELECT record_created_at::TIMESTAMP AS event_time, 'CRM record created' AS title,
        'A person is known to CRM; this is not yet a paid acquisition.' AS detail, 'crm' AS lane
      FROM people WHERE person_id='{literal}'
      UNION ALL SELECT occurred_at::TIMESTAMP, replace(event_type,'_',' '),
        'Observed interaction on ' || platform || '; motive is not supplied.', 'product'
      FROM product_events WHERE person_id='{literal}'
      UNION ALL SELECT occurred_at::TIMESTAMP, transaction_type || ': ' || charge_type,
        'Financial event ' || transaction_id || '; refunds remain separate ledger events.', 'billing'
      FROM transactions WHERE person_id='{literal}'
      UNION ALL SELECT submitted_at::TIMESTAMP, 'Customer feedback',
        coalesce(main_difficulty,'No coded difficulty supplied') || '; a reported perception, not a measured cause.', 'feedback'
      FROM feedback WHERE person_id='{literal}'
    ) SELECT event_time,title,detail,lane FROM observations,first_paid
      WHERE event_time<=first_paid_at + INTERVAL '30 days'
      ORDER BY event_time,lane,title LIMIT 14"""
    sql_log.append(query); rows=con.execute(query).fetchall()
    events=[]
    for i,(at,title,detail,lane) in enumerate(rows):
        stamp=at.isoformat(timespec="seconds")+"Z"
        events.append({"id":f"event{i}","at":stamp,"title":str(title),"detail":str(detail),"lane":lane})
    return {"schema_version":1,"diagram_type":"timeline","meta":{"title":f"One observed customer journey: {person}","output":"customer-journey.html","locale":"en","quality_profile":"showcase","evidence":"observed","timezone":"UTC"},
            "lanes":[{"id":"crm","label":"CRM"},{"id":"product","label":"Product"},{"id":"billing","label":"Billing"},{"id":"feedback","label":"Feedback"}],"events":events,
            "cards":[{"dot":"emerald","title":"Observed in synthetic records","items":["The timeline displays recorded actions and responses for one person; the source data are fictional.","The first 30 days after payment are selected for readability; this is not a population funnel."]},
                     {"dot":"orange","title":"What the records do not say","items":["A product event does not establish motivation. A survey response is a perception, not a causal explanation.","Other touchpoints and unreported experiences remain unknown. These records suggest questions to investigate."]}]}


def _conceptual_journey(need: str) -> dict:
    """A segment-specific hypothesis, deliberately distinct from observed events."""
    if need not in {"save_time", "build_skill"}:raise ValueError("Unknown pre-acquisition need segment")
    short=need.replace("_","-")
    if need=="save_time":
        title="Save time: a conceptual customer journey"
        actions=[("Recognize friction","repetitive task feels costly"),("Evaluate fit","compare ease and effort"),("Get first value","complete one useful task"),("Build a routine","repeat with less effort"),("Review renewal","is the time saving worth it?")]
        questions=["Hypothesis: a shorter route to first useful output matters more than feature breadth.","Investigate: among people who state save_time, which onboarding steps delay their first useful action?", "Ask in research: what task did you hope to complete, how long did it take, and what remained difficult?"]
    else:
        title="Build skill: a conceptual customer journey"
        actions=[("Set a learning goal","identify a capability gap"),("Evaluate guidance","look for useful practice"),("Try the first lesson","complete guided practice"),("Notice progress","apply a learned skill"),("Review renewal","is there a useful next step?")]
        questions=["Hypothesis: visible progress and a credible next challenge matter more than immediate speed.","Investigate: among people who state build_skill, does the observed sequence include practice and return visits?", "Ask in research: what did you want to learn, what can you do now, and where did you get stuck?"]
    evidence=[("Need + source","CRM / attributed source"),("Early interactions","product event sequence"),("Payment + usage","billing / product events"),("Experience + voice","events / feedback"),("Continue or leave","renewal system / billing")]
    nodes=[];edges=[]
    for i,((label,sub),(data_label,data_sub)) in enumerate(zip(actions,evidence)):
        nodes.extend([{"id":f"step{i}","lane":"hypothesis","col":i,"type":"frontend","label":label,"sublabel":sub,"width":180},
                      {"id":f"evidence{i}","lane":"evidence","col":i,"type":"database","label":data_label,"sublabel":data_sub,"width":180}])
        if i:edges.append({"id":f"sequence{i}","from":f"step{i-1}","to":f"step{i}","variant":"default"})
        edges.append({"id":f"look{i}","from":f"step{i}","to":f"evidence{i}","variant":"dashed"})
    return {"schema_version":2,"diagram_type":"workflow","meta":{"title":title,"subtitle":"Hypotheses to examine, not an observed path or a population funnel","output":f"journey-{short}.html","locale":"en","quality_profile":"standard","visual_preset":"editorial","animation":"none",
            "legend":{"entries":{"frontend":{"label":"Proposed experience"},"database":{"label":"Evidence source"}}}},
            "lanes":[{"id":"hypothesis","label":"Conceptual customer experience"},{"id":"evidence","label":"Where to look for evidence"}],
            "nodes":nodes,"edges":edges,
            "cards":[{"dot":"orange","title":"Proposed interpretation — test it","items":questions},
                     {"dot":"cyan","title":"What is recorded and what is missing","items":["The stated need is recorded before acquisition. It is a segment definition, not proof of motives at every later stage.","The records supply actions, payments, renewal outcomes and selected perceptions. The arrows do not establish causality or a universal order.","Unlike a funnel, this map does not report a population conversion rate. Compare it with the separate observed timeline before designing a survey or intervention."]}]}


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
    candidates={"source-systems":_system_candidate(inventory),"source-tables":_erd_candidate(),"source-tables-report":_report_erd_candidate(),"source-systems-report":_report_system_candidate(),"customer-journey":_journey_candidate(con,sql_log),
                "journey-save-time":_conceptual_journey("save_time"),"journey-build-skill":_conceptual_journey("build_skill")}
    con.close()
    (folder/"inspection.sql").write_text(";\n\n".join(s.rstrip(';') for s in sql_log)+";\n",encoding="utf-8")
    _write(folder/"source_inventory.json",inventory)
    ucv_tables=build_ucv_tables(data)
    _write(folder/"ucv-tables.json",{"framework":"Universal Customer View","categories":["Identifiers","Engagement","Relationship","Perception"],"tables":ucv_tables})
    (folder/"ucv-tables.md").write_text(ucv_markdown(ucv_tables),encoding="utf-8")
    results={}
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
    static_stems=("source-systems","source-tables","source-tables-report","source-systems-report")
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
    result={"archify":_json_provenance(),"sources":inventory,"diagrams":results,
            "static_renderer":{"package":"playwright","version":"1.62.1","viewport":[2400,1600],"device_scale_factor":2,"theme":"light","animations":"disabled","locale":"en-US","timezone":"UTC","report_overview":"Native nodes and edges; reader swimlanes/legend omitted; 12px titles and 9px context; cropped with 20px margin"},
            "ucv":{"json":"diagrams/ucv-tables.json","markdown":"diagrams/ucv-tables.md"},
            "output_hashes":{p.relative_to(output).as_posix():_sha(p) for p in outputs},
            "verification":"Native renderer validation passed; browser and visual review are separate development checks."}
    _write(folder/"diagram_manifest.json",result)
    return result


def _json_provenance():
    return json.loads((ROOT/"vendor/archify-provenance.json").read_text(encoding="utf-8"))
