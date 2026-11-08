import json
from pathlib import Path
import pytest
from cohort_lab.debrief import initialize, record, snapshot, prepare, normalized_usage, fallback_feedback, render_portable


def workspace(tmp_path, name="learner", route="personal"):
    root = tmp_path/name; root.mkdir()
    (root/"lesson_state.json").write_text(json.dumps({"completed_step": 5, "messages": [
        {"text": "What separates a cohort from a segment?", "step": 5, "explicit_next_step": False}]}))
    (root/"learner_choices.json").write_text(json.dumps({"segmentation_rationale": "Compare within-cell dispersion at matched age."}))
    initialize(root, route=route, harness="Codex")
    return root


def receipt(key, value=100, mode="call", sequence=None, stream="harness-1", scope="harness"):
    item = {"event_id": key, "kind": "usage", "provider": "openai", "model": "fixture-model",
            "meter_scope": scope, "stream_id": stream, "mode": mode, "source": "fixture receipt",
            "semantics": "openai_inclusive", "usage": {"input_tokens": value, "output_tokens": value//2}}
    if sequence is not None: item["sequence"] = sequence
    return item


def test_received_text_and_replays_are_local(tmp_path):
    a=workspace(tmp_path,"a"); b=workspace(tmp_path,"b", "university_mcp")
    event={"event_id":"reply-1","kind":"text","role":"assistant","text":"A cohort shares an acquisition month."}
    assert record(a,event)
    assert not record(a,event)
    with pytest.raises(ValueError,match="Conflicting"):
        record(a,{**event,"text":"Changed"})
    pa,pb=snapshot(a),snapshot(b)
    assert pa["snapshot_id"] != pb["snapshot_id"]
    assert pa["metrics"]["recorded_text_estimate"]["utf8_bytes"] > pb["metrics"]["recorded_text_estimate"]["utf8_bytes"]
    assert pa["metrics"]["full_session_inference_tokens"] is None
    assert "run_id" not in pa and "session_id" not in pa


def test_actual_provider_token_semantics():
    raw={"input_tokens":100,"output_tokens":20,"cache_read_input_tokens":40,"cache_creation_input_tokens":10}
    assert normalized_usage(raw,"openai_inclusive")["total_tokens"] == 120
    assert normalized_usage(raw,"anthropic_input_excludes_cache")["total_tokens"] == 170
    assert normalized_usage({"input_tokens":100,"output_tokens":20},"anthropic_input_excludes_cache")["total_tokens"] is None
    with pytest.raises(ValueError): normalized_usage({"input_tokens":True},"openai_inclusive")


def test_cumulative_baseline_and_separate_scopes(tmp_path):
    root=workspace(tmp_path)
    record(root,receipt("base",1000,"cumulative",0))
    assert snapshot(root)["metrics"]["usage_streams"][0]["total_tokens"] is None
    record(root,receipt("end",1600,"cumulative",1))
    record(root,receipt("mcp-call",200,stream="unc-1",scope="university_mcp"))
    streams=snapshot(root)["metrics"]["usage_streams"]
    assert {r["scope"]:r["total_tokens"] for r in streams} == {"harness":900,"university_mcp":300}
    assert snapshot(root)["metrics"]["full_session_inference_tokens"] is None


def test_reset_or_overlapping_accounting_is_rejected(tmp_path):
    a=workspace(tmp_path,"reset")
    record(a,receipt("start",1000,"cumulative",0));record(a,receipt("later",500,"cumulative",1))
    with pytest.raises(ValueError,match="reset"): snapshot(a)
    b=workspace(tmp_path,"mixed")
    record(b,receipt("start",1000,"cumulative",0));record(b,receipt("call",500))
    with pytest.raises(ValueError,match="mix"): snapshot(b)


def test_frozen_feedback_replay_preserves_review(tmp_path):
    root=workspace(tmp_path)
    result=prepare(root)
    path=Path(result["debrief"]); packet=json.loads(Path(result["evidence"]).read_text())
    response=fallback_feedback(packet)
    (path.parent/"feedback-reviewed.json").write_text(json.dumps(response))
    render_portable(packet,response,path=path,provenance={"model":"reviewed fixture"})
    reviewed=path.read_bytes()
    assert prepare(root)["snapshot_id"] == result["snapshot_id"]
    assert path.read_bytes() == reviewed
    event={"event_id":"reply-2","kind":"text","role":"assistant","text":"Now inspect matched-age outcomes."}
    record(root,event)
    assert prepare(root)["snapshot_id"] != result["snapshot_id"]
    assert path.read_bytes() == reviewed


def test_missing_usage_and_untrusted_text_render_honestly(tmp_path):
    root=workspace(tmp_path)
    record(root,{"event_id":"xss","kind":"text","role":"assistant","text":"<script>alert(1)</script>"})
    result=prepare(root)
    text=Path(result["debrief"]).read_text()
    assert "Provider-measured token usage: unavailable" in text
    assert "Recorded-text estimate" in text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_feedback_packet_does_not_export_accounting_identifiers(tmp_path):
    root=workspace(tmp_path)
    record(root,receipt("private",stream="student@example.edu"))
    packet=snapshot(root)
    assert packet["metrics"]["usage_streams"][0]["stream_id"] == "stream-1"
    assert "student@example.edu" not in json.dumps(packet)
