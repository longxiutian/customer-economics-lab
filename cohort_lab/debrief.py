"""Portable personal debriefs for local agents and university-funded agent routes.

No API call, credential discovery, account scan, or message sending occurs here.
StudentWorkflow saves learner messages; the harness records its visible replies
and any usage receipts it can actually obtain for this lab session.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import html
import json
import math
from pathlib import Path
import time
import uuid

from hosting.telemetry import Telemetry, canonical, redact, sha
from hosting.student_debrief import RUBRIC, RUBRIC_VERSION, validate_response

ROUTES = {"personal", "university_mcp", "longleaf"}


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def initialize(output, *, route, harness):
    output = Path(output).resolve()
    if route not in ROUTES or not isinstance(harness, str) or not harness.strip():
        raise ValueError("Choose personal, university_mcp or longleaf and name the actual harness.")
    if not any((output / name).is_file() for name in ("lesson_state.json", "lab_state.json", "automatic_run.json")):
        raise ValueError("Start the lesson first, then initialize logging in that same output folder.")
    path = output / "usage/session.json"
    if path.exists():
        prior = read(path)
        if prior["route"] != route or prior["harness"] != harness:
            raise ValueError("This workspace already has a different route; preserve its usage record.")
        return prior
    session = {"schema_version": 1, "run_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4()),
               "route": route, "harness": harness, "created_at": time.time()}
    write(path, session)
    return session


def session(output):
    value = read(Path(output) / "usage/session.json")
    if not value:
        raise ValueError("Initialize this workspace's personal-debrief logging first.")
    return value


def count(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("Token counters must be nonnegative integers or null.")
    return value


def normalized_usage(raw, semantics):
    """Return inclusive input/output counts; preserve missing values as unknown."""
    if semantics not in {"openai_inclusive", "anthropic_input_excludes_cache"}:
        raise ValueError("Declare the receipt's input/cache semantics.")
    inp, out = count(raw.get("input_tokens")), count(raw.get("output_tokens"))
    cache = count(raw.get("cache_read_input_tokens"))
    create = count(raw.get("cache_creation_input_tokens"))
    if semantics == "anthropic_input_excludes_cache":
        inp = inp + cache + create if all(v is not None for v in (inp, cache, create)) else None
    return {"input_tokens": inp, "output_tokens": out,
            "total_tokens": inp + out if inp is not None and out is not None else None}


def record(output, item):
    output = Path(output)
    s = session(output)
    kind = item.get("kind")
    if kind == "text":
        if item.get("role") not in {"assistant", "tool"} or not isinstance(item.get("text"), str):
            raise ValueError("Record visible assistant/tool text; learner messages come from lesson_state.json.")
        payload = {k: item[k] for k in ("role", "text")}
        payload["scope"] = item.get("scope", "lab")
        if payload["scope"] not in {"lab", "debrief"}:
            raise ValueError("Text scope must be lab or debrief.")
    elif kind == "usage":
        required = {"provider", "model", "meter_scope", "stream_id", "mode", "source", "usage", "semantics"}
        if not required <= item.keys() or item["mode"] not in {"call", "cumulative"}:
            raise ValueError("A usage receipt needs its provider, model, scope, stream, mode, source and counters.")
        if not all(isinstance(item[k], str) and item[k].strip() for k in required - {"usage"}):
            raise ValueError("Usage labels must be nonempty strings.")
        normalized_usage(item["usage"], item["semantics"])
        payload = {k: item[k] for k in required}
        payload["usage"] = {k: count(item["usage"].get(k)) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        if item["mode"] == "cumulative":
            payload["sequence"] = count(item.get("sequence"))
            if payload["sequence"] is None:
                raise ValueError("Cumulative snapshots need increasing sequence numbers; first is the baseline.")
    else:
        raise ValueError("Record kind must be text or usage.")
    ledger = Telemetry(output / "usage/events.sqlite")
    # Use a stable harness turn/provider response ID. Repeating it is idempotent.
    return ledger.append(event_id=item["event_id"], run_id=s["run_id"], session_id=s["session_id"],
                         kind=kind, happened_at=item.get("happened_at", 0), payload=payload)


def usage_summary(events):
    groups = defaultdict(list)
    for event in events:
        if event["kind"] == "usage":
            p = event["payload"]
            groups[tuple(p[k] for k in ("meter_scope", "provider", "model", "stream_id"))].append(p)
    rows = []
    for (scope, provider, model, stream), items in sorted(groups.items()):
        modes = {p["mode"] for p in items}
        semantics = {p["semantics"] for p in items}
        if len(modes) != 1 or len(semantics) != 1:
            raise ValueError("Do not mix cumulative and per-call accounting or token semantics in a stream.")
        mode = items[0]["mode"]
        values = [normalized_usage(p["usage"], p["semantics"]) for p in items]
        result = {"scope": scope, "provider": provider, "model": model, "stream_id": stream,
                  "mode": mode, "receipts": len(items), "coverage": "Recorded receipts only; completeness is not inferred."}
        if mode == "call":
            for field in ("input_tokens", "output_tokens", "total_tokens"):
                result[field] = sum(v[field] for v in values) if all(v[field] is not None for v in values) else None
        else:
            ordered = sorted(items, key=lambda p: p["sequence"])
            if len({p["sequence"] for p in ordered}) != len(ordered):
                raise ValueError("Duplicate cumulative sequence; reconcile the receipts.")
            values = [normalized_usage(p["usage"], p["semantics"]) for p in ordered]
            for field in ("input_tokens", "output_tokens", "total_tokens"):
                known = [v[field] for v in values]
                if any(a is not None and b is not None and b < a for a, b in zip(known, known[1:])):
                    raise ValueError("Counter reset detected; start a new stream with its own baseline.")
                result[field] = known[-1] - known[0] if len(known) >= 2 and all(v is not None for v in known) else None
            result["coverage"] = "Delta from the first baseline to the last recorded counter; earlier/later usage is excluded."
        rows.append(result)
    return rows


def visible_estimate(texts):
    size = sum(len(t.encode("utf-8")) for t in texts)
    return {"utf8_bytes": size, "estimate": math.ceil(size / 4),
            "heuristic_range": [math.ceil(size / 6), math.ceil(size / 2)],
            "method": "UTF-8 bytes / 4, with 2–6 bytes/token sensitivity range for recorded text; not a statistical interval.",
            "scope": "Text-volume proxy only. Excludes repeated context, hidden instructions/reasoning and unrecorded tool traffic; not inference usage, billing or plan quota."}


def snapshot(output, *, private_terms=()):
    output = Path(output).resolve()
    s = session(output)
    events = Telemetry(output / "usage/events.sqlite").events(s["run_id"], s["session_id"])
    lesson = read(output / "lesson_state.json", {})
    automatic = read(output / "automatic_run.json", {})
    if lesson and automatic:
        raise ValueError("Keep the automatic trial in a separate workspace from a guided lesson.")
    if automatic and automatic.get("mode") != "automatic-trial":
        raise ValueError("Unrecognized automatic-run record.")
    choices = read(output / "learner_choices.json", {})
    if automatic and choices:
        raise ValueError("Automatic trial outputs must not contain synthesized learner judgments.")
    prompts = (automatic or lesson).get("messages", [])
    texts = [p["text"] for p in prompts]
    texts += [e["payload"]["text"] for e in events if e["kind"] == "text" and e["payload"]["scope"] == "lab"]
    files = {}
    for name in ("model_manifest.json", "report/report_manifest.json", "report/customer-economics-report.pdf"):
        p = output / name
        if p.is_file():
            import hashlib
            files[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    lesson_identity = {k: lesson.get(k) for k in ("completed_step", "messages", "inputs", "implementation", "invalidations")}
    if automatic:
        lesson_identity = {k: automatic.get(k) for k in ("mode", "status", "messages", "inputs", "implementation", "completed_stages")}
    sid = sha({"session": s, "events": [e["digest"] for e in events], "lesson": lesson_identity,
               "choices": choices, "artifacts": files})[:24]
    streams = usage_summary(events)
    for i, row in enumerate(streams, 1):
        # Accounting IDs can contain private account labels; retain them only in the ledger.
        row["stream_id"] = f"stream-{i}"
        for key in ("scope", "provider", "model"):
            row[key] = redact(row[key], private_terms=private_terms)
    metrics = {"route": s["route"], "harness": redact(s["harness"], private_terms=private_terms), "lab_requests": len(prompts),
               "saved_judgments": len(choices), "checkpoint": lesson.get("completed_step"),
               "usage_streams": streams, "recorded_text_estimate": visible_estimate(texts),
               "full_session_inference_tokens": None}
    if automatic:
        metrics["execution_mode"] = "automatic-trial"
        metrics["completed_analytical_stages"] = automatic.get("completed_stages", [])
    coverage = {"usage": "Measured receipt streams and estimated recorded text are separate. Never add them or convert a subscription percentage into tokens.",
                "questions": "Actual learner messages saved by the guided lesson; assistant/tool text only when the harness recorded it.",
                "route": "The personal/university MCP route can edit a local/cloud checkout. The hosted Longleaf route exposes its verified server tools only.",
                "privacy": "This packet excludes private run/session IDs. It is local by default; no class-wide export or delivery occurs.",
                "debrief_usage": "Feedback-generation usage is a separate scope and may arrive after this snapshot."}
    if automatic:
        coverage["questions"] = "Actual starting request from automatic_run.json; visible assistant/tool text only when recorded. No checkpoint interaction was requested or simulated."
        coverage["recommendation"] = "The report contains an analyst recommendation. This automatic run does not establish the student's own reasoning or learning."
    evidence = []
    def add(kind, text, source):
        evidence.append({"id": f"snap:{sid}/ev:{len(evidence)+1}", "kind": kind,
                         "text": redact(text, private_terms=private_terms), "source": source})
    add("metrics", canonical(metrics), "saved lab state and explicitly recorded usage")
    for p in prompts:
        if not p.get("explicit_next_step"):
            add("prompt_excerpt", p["text"][:2500], "actual request in automatic_run.json" if automatic else "learner message in lesson_state.json")
    for key, value in choices.items():
        add("saved_judgment", f"{key}: {value}", "learner_choices.json")
    for name, digest in files.items():
        add("artifact", f"Saved artifact {name}; SHA-256 {digest}", "workspace file hash")
    for e in [e for e in events if e["kind"] == "text" and e["payload"]["role"] == "assistant" and e["payload"]["scope"] == "lab"][-2:]:
        add("model_excerpt", e["payload"]["text"][:2200], "recorded visible assistant reply; not independently verified")
    return {"schema_version": 2, "snapshot_id": sid, "fixture": False,
            "metrics": metrics, "coverage": coverage, "evidence": evidence}


def fallback_feedback(packet):
    """A transparent, deterministic scaffold; the student's agent reviews/refines it."""
    first = packet["evidence"][0]["id"]
    choice = next((e for e in packet["evidence"] if e["kind"] == "saved_judgment"), None)
    ref = choice["id"] if choice else first
    m = packet["metrics"]
    note = "A saved judgment reads: " + " ".join(choice["text"].split()[:43]) if choice else "No analytical judgment is present in this snapshot. Save your own interpretation before using it to recommend a management action."
    def recommendation(text, prompt, refs):
        return {"text": text, "prompt": prompt, "evidence_ids": refs}
    return {"rubric_version": RUBRIC_VERSION, "snapshot_id": packet["snapshot_id"],
            "observations": [
                {"text": f"The saved lesson contains {m['lab_requests']} learner messages and {m['saved_judgments']} analytical judgments. These describe the available record, not your learning quality.", "evidence_ids": [first], "quote": ""},
                {"text": note, "evidence_ids": [ref], "quote": ""}],
            "studio_north_next_steps": [
                recommendation("Test whether your proposed segments separate customer economics at comparable cohort ages.", "Compare within-cell dispersion and across-cell differences in retention and contribution at the same age. Show the executed SQL and explain whether the segmentation earns its complexity.", [ref]),
                recommendation("Connect the recommendation to current channel incrementality and contribution value.", "For each candidate segment, put LTV before acquisition cost beside current holdout-based iCAC. Explain the marginal-customer assumption and what would change my recommendation.", [ref])],
            "ai_learning_next_steps": [
                recommendation("Practice checking a recommendation against its source evidence.", "Choose one claim from our discussion. Trace it to saved SQL, a table or a report exhibit; distinguish my judgment from your interpretation.", [first]),
                recommendation("Use the activity record to improve how you ask questions, while preserving uncertainty about unobserved usage.", "Review my recorded questions and replies. Propose one more specific follow-up question and one unnecessary repetition to avoid, only if the record supports it. Separate measured tokens, text estimates and unknown usage.", [first])]}


def render_portable(packet, response, *, path, provenance=None):
    validate_response(packet, response)
    esc = html.escape
    m = packet["metrics"]
    parts = ["<h1>Your Studio North lab debrief</h1>", f"<p>{esc(m['harness'])} · {esc(m['route'])}</p>",
             "<h2>Your recorded AI activity</h2>",
             f"<p>{m['lab_requests']} learner messages · {m['saved_judgments']} saved judgments · " +
             ("automatic trial; no teaching checkpoints" if m.get('execution_mode') == 'automatic-trial' else f"checkpoint {m['checkpoint']}") + "</p>"]
    if not m["usage_streams"]:
        parts.append("<p>Provider-measured token usage: unavailable in this record.</p>")
    for row in m["usage_streams"]:
        total = f"{row['total_tokens']:,}" if row["total_tokens"] is not None else "unknown"
        parts.append(f"<p><b>{esc(row['scope'])} / {esc(row['provider'])} / {esc(row['model'])}</b>: {total} measured tokens. {esc(row['coverage'])}</p>")
    estimate = m["recorded_text_estimate"]
    parts.append(f"<p>Recorded-text estimate: approximately {estimate['estimate']:,} tokens; heuristic range {estimate['heuristic_range'][0]:,}–{estimate['heuristic_range'][1]:,}. {esc(estimate['scope'])}</p>")
    for key, heading in (("observations", "Your recorded approach"), ("studio_north_next_steps", "Take Studio North further"), ("ai_learning_next_steps", "Build your AI practice")):
        parts.append(f"<h2>{heading}</h2>")
        for row in response[key]:
            refs = ", ".join(r.split('/ev:')[-1] for r in row["evidence_ids"])
            parts.append(f"<p>{esc(row['text'])} <small>[Evidence {refs}]</small></p>")
            if row.get("prompt"):
                parts.append(f"<blockquote>{esc(row['prompt'])}</blockquote>")
    parts.append("<h2>Evidence and coverage</h2>")
    for value in packet["coverage"].values():
        parts.append(f"<p>{esc(value)}</p>")
    for e in packet["evidence"]:
        parts.append(f"<h3>Evidence {esc(e['id'].split('/ev:')[-1])}</h3><pre>{esc(e['text'])}</pre>")
    parts.append("<pre>" + esc(json.dumps(provenance or {}, indent=2)) + "</pre>")
    css = "body{font:16px/1.5 Arial;max-width:850px;margin:40px auto;padding:0 24px;color:#13294b}h2{color:#155b88;margin-top:30px}blockquote{border-left:4px solid #4b9cd3;padding:12px;background:#e8f2f9;margin:15px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 Arial}small{color:#627488}"
    Path(path).write_text("<!doctype html><html lang='en'><meta charset='utf-8'><title>Studio North personal debrief</title><style>" + css + "</style><body>" + "\n".join(parts) + "</body></html>", encoding="utf-8", newline="\n")


def prepare(output):
    output = Path(output)
    packet = snapshot(output)
    folder = output / "debrief" / packet["snapshot_id"]
    write(folder / "evidence-packet.json", packet)
    (folder / "feedback-request.txt").write_text(RUBRIC + "\nEVIDENCE JSON:\n" + json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    response = read(folder / "feedback-reviewed.json") or fallback_feedback(packet)
    if not (folder / "feedback-reviewed.json").exists():
        write(folder / "feedback-scaffold.json", response)
    if not (folder / "feedback-reviewed.json").exists():
        render_portable(packet, response, path=folder / "personal-debrief.html",
                        provenance={"status": "Deterministic scaffold; the current agent should review and personalize it. No Opus call is claimed.", "snapshot_id": packet["snapshot_id"]})
    result = {"snapshot_id": packet["snapshot_id"], "evidence": str(folder / "evidence-packet.json"),
              "request": str(folder / "feedback-request.txt"), "debrief": str(folder / "personal-debrief.html")}
    write(output / "debrief/latest.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    commands = p.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("--route", choices=sorted(ROUTES), required=True); init.add_argument("--harness", required=True)
    rec = commands.add_parser("record"); rec.add_argument("--file", type=Path, required=True)
    commands.add_parser("prepare")
    finish = commands.add_parser("render"); finish.add_argument("--snapshot", type=Path, required=True); finish.add_argument("--response", type=Path, required=True); finish.add_argument("--model", required=True)
    a = p.parse_args()
    if a.command == "init":
        initialize(a.output, route=a.route, harness=a.harness); result = {"initialized": True, "route": a.route, "harness": a.harness}
    elif a.command == "record": result = {"appended": record(a.output, read(a.file))}
    elif a.command == "prepare": result = prepare(a.output)
    else:
        packet, response = read(a.snapshot), read(a.response)
        latest = read(a.output / "debrief/latest.json")
        if not latest or latest["snapshot_id"] != packet["snapshot_id"] or Path(latest["evidence"]).resolve() != a.snapshot.resolve():
            raise ValueError("Use this workspace's current frozen evidence packet.")
        validate_response(packet, response)
        target = a.snapshot.parent / "personal-debrief.html"
        write(a.snapshot.parent / "feedback-reviewed.json", response)
        render_portable(packet, response, path=target, provenance={"model": a.model, "review": "Evidence IDs and exact quotes validated; agent must also review claims", "snapshot_id": packet["snapshot_id"]})
        result = {"debrief": str(target), "validated": True}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
