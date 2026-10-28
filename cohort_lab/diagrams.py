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
        {"id":"crm","type":"database","label":"CRM","sublabel":"people","stage":0,"row":0},
        {"id":"billing","type":"database","label":"Billing + renewal","sublabel":"financial records","stage":0,"row":1},
        {"id":"experience","type":"database","label":"Experience","sublabel":"events / feedback","stage":0,"row":2},
        {"id":"marketing","type":"database","label":"Marketing","sublabel":"spend / credit","stage":0,"row":3},
        {"id":"assignments","type":"database","label":"Assignments","sublabel":"eligible prospects","stage":0,"row":4},
        {"id":"raw","type":"database","label":"Raw SQL views","sublabel":"separate grains","stage":1,"row":2,"height":104},
        {"id":"cohorts","type":"backend","label":"Cohort economics","sublabel":"person / age / cost","stage":2,"row":1},
        {"id":"experiment","type":"backend","label":"Experiment means","sublabel":"all assigned people","stage":2,"row":3},
        {"id":"forecast","type":"backend","label":"Value model","sublabel":"observed + future","stage":3,"row":1},
        {"id":"effects","type":"backend","label":"Tested effects","sublabel":"own control window","stage":3,"row":3},
        {"id":"decision","type":"backend","label":"Report","sublabel":"evidence to action","stage":4,"row":2},
    ]
    edges=[("crm","raw","person + need"),("billing","raw","paid / retained"),("experience","raw","events / reports"),
           ("marketing","raw","cost + credit"),("assignments","raw","all assignments"),
           ("raw","cohorts","customer values"),("raw","experiment","roster + outcomes"),
           ("experiment","effects","arm comparison"),("cohorts","forecast","cohort histories"),
           ("effects","decision","tested effects"),("forecast","decision","predicted value")]
    return {"schema_version":1,"diagram_type":"dataflow","meta":{"title":"Separate systems, explicit meanings, connected evidence","output":"source-systems.html","locale":"en","quality_profile":"standard"},
        "stages":[{"label":"Raw CSV exports"},{"label":"DuckDB source views"},{"label":"Saved SQL tables"},{"label":"Different evidence"},{"label":"Interpret and act"}],
        "nodes":nodes,"flows":[{"id":f"flow{i}","from":a,"to":b,"label":label} for i,(a,b,label) in enumerate(edges)],
        "cards":[{"dot":"emerald","title":"Same key, different grains","items":[f"{x['file']}: {x['rows']:,} rows; {x['grain']}" for x in inventory[:4]]},
                 {"dot":"orange","title":"The denominator is a business choice","items":[f"{x['file']}: {x['rows']:,} rows; {x['grain']}" for x in inventory[4:]]},
                 {"dot":"cyan","title":"Meaning must survive each join","items":["The shared person_id is documented; IDs for orders, periods and events identify other objects.","Aggregate each source at its intended grain before joining; daily spend must not repeat on transaction rows.","The experiment begins with all assigned eligible people. No purchase is an observed zero, not an omitted row."]}]}


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
    candidates={"source-systems":_system_candidate(inventory),"customer-journey":_journey_candidate(con,sql_log),
                "journey-save-time":_conceptual_journey("save_time"),"journey-build-skill":_conceptual_journey("build_skill")}
    con.close()
    (folder/"inspection.sql").write_text(";\n\n".join(s.rstrip(';') for s in sql_log)+";\n",encoding="utf-8")
    _write(folder/"source_inventory.json",inventory)
    results={}
    for stem,candidate in candidates.items():
        source=folder/f"{stem}.json";dest=folder/f"{stem}.html";_write(source,candidate)
        kind=candidate["diagram_type"]
        renderer=vendor/"renderers"/kind/f"render-{kind}.mjs"
        p=subprocess.run([node,str(renderer),str(source),str(dest)],cwd=folder,text=True,capture_output=True,timeout=120)
        (folder/f"{stem}.render.log").write_text(p.stdout+p.stderr,encoding="utf-8")
        if p.returncode or not dest.exists():raise RuntimeError(f"Archify {kind} render failed: "+(p.stdout+p.stderr)[-3500:])
        results[stem]={"json":f"diagrams/{source.name}","html":f"diagrams/{dest.name}","sha256":_sha(dest),"renderer":"native Archify "+kind}
    result={"archify":_json_provenance(),"sources":inventory,"diagrams":results,"verification":"Native renderer validation passed; browser and visual review are separate development checks."}
    _write(folder/"diagram_manifest.json",result)
    return result


def _json_provenance():
    return json.loads((ROOT/"vendor/archify-provenance.json").read_text(encoding="utf-8"))
