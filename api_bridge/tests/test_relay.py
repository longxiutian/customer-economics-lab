"""Actual stdio plus setup/debrief integration. No provider is contacted."""
import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest

from test_bridge import KEY, REPO, Upstream, answer, ask, make_bridge, make_config, seed
from unc_sol_bridge.config import BridgeError, load_config
from unc_sol_bridge.packets import compile_packet
from unc_sol_bridge.relay import call
from unc_sol_bridge.server import build_server
from unc_sol_bridge.setup import prepare


def test_stdio_missing_auth_is_local_and_extra_models_are_rejected(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    seed(config, 0)
    monkeypatch.delenv("UNC_SOL_TEST_KEY", raising=False)
    result = asyncio.run(call(config.path, "sol_status", None))
    assert result["checkpoint"]["step"] == 0 and result["provider_called"] is False
    preview = asyncio.run(call(config.path, "sol_preview", {"intent": "open"}))
    assert preview["reservation_tokens"] < 10000 and not preview["provider_called"]
    forbidden = asyncio.run(call(config.path, "sol_ask", {
        "request_id": "stdio-luna", "intent": "open", "model": "gpt-6-luna"}))
    assert forbidden["kind"] == "invalid_arguments" and not forbidden["provider_called"]
    missing = asyncio.run(call(config.path, "sol_ask", {"request_id": "stdio-auth", "intent": "open"}))
    assert missing["kind"] == "credential_unavailable" and not missing["provider_called"]
    status = asyncio.run(call(config.path, "sol_status", {}))
    assert status["budget"]["settled"] == status["budget"]["outstanding"] == 0


def test_tool_schema_and_runtime_both_reject_extras_and_coercion(tmp_path):
    config = make_config(tmp_path)
    server = build_server(config.path)
    tools = asyncio.run(server.list_tools())
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools)
    for name, args in (("sol_status", {"unused": 1}),
                       ("sol_ask", {"request_id": "strict-001", "intent": "open", "learner_text": 123})):
        result = asyncio.run(server.call_tool(name, args))
        assert result.is_error and result.structured_content["kind"] == "invalid_arguments"


def test_test_release_cannot_be_promoted_by_editing_configuration(tmp_path, monkeypatch):
    from unc_sol_bridge import config
    monkeypatch.setattr(config, "RELEASE_PHASES", frozenset({"startup"}))
    with pytest.raises(BridgeError) as caught:
        make_config(tmp_path, phase="full", stage_cap=400000)
    assert caught.value.kind == "phase_not_released"


def test_partial_output_is_retained_privately_and_subset_counts_are_not_added(tmp_path):
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream(answer("Partial interpretation", status="incomplete",
                               incomplete_details={"reason": "max_output_tokens"}))
    bridge = make_bridge(config, upstream)
    result = ask(bridge, request_id="partial-001", intent="open")
    assert "text" not in result and result["kind"] == "incomplete"
    assert (bridge.local / "partial-001.txt").read_text() == "Partial interpretation"
    assert result["usage"]["reasoning_tokens"] == 400 and result["usage"]["charge"] == 1800


def test_actual_credential_and_generic_apim_shape_cannot_enter_packet(tmp_path):
    config = make_config(tmp_path, phase="pilot", stage_cap=100000)
    seed(config, 0)
    upstream = Upstream()
    bridge = make_bridge(config, upstream)
    known = ask(bridge, request_id="secret-001", intent="question", learner_text=KEY)
    assert known["kind"] == "credential_in_packet" and upstream.calls == 0
    shaped = ask(bridge, request_id="secret-002", intent="question", learner_text="a" * 32)
    assert shaped["kind"] == "secret_shaped_input" and upstream.calls == 0
    assert bridge.ledger.get("secret-001") is bridge.ledger.get("secret-002") is None


class MemoryKeyring:
    def __init__(self):
        self.entries = {}

    def set_password(self, service, name, value):
        self.entries[service, name] = value


def test_prepare_runs_real_opening_and_logging_without_dependencies_or_inference(tmp_path, monkeypatch):
    from unc_sol_bridge import setup
    private = tmp_path / "private"
    private.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: private))
    vault = MemoryKeyring()
    monkeypatch.setattr(setup, "_keyring", lambda: vault)
    credential = private / "student.credentials.json"
    credential.write_text(json.dumps({
        "subscription": "offline-integration", "period_id": time.strftime("%Y-%m", time.gmtime()),
        "baseline_tokens": 1700, "baseline_source": "known earlier activity in this unit fixture",
        "primary_key": KEY,
    }), encoding="utf-8")
    config_path, run = private / "config.json", tmp_path / "real-guided-opening"
    result = prepare(config_path=config_path, source_root=REPO, run_dir=run,
                     credential_file=credential, harness="offline-test-harness")
    assert result["checkpoint"]["step"] == 0 and result["budget"]["baseline"] == 1700
    assert not result["provider_called"] and not (run / "lab_state.json").exists()
    assert not list(run.rglob("*.pdf")) and not (run / "model_manifest.json").exists()
    assert json.loads((run / "usage/session.json").read_text())["route"] == "university_mcp"
    assert KEY not in config_path.read_text() and len(vault.entries) == 1
    before = (run / "lesson_state.json").read_bytes()
    credential.unlink()
    again = prepare(config_path=config_path, source_root=REPO, run_dir=run,
                    credential_file=credential, harness="offline-test-harness")
    assert not again["provider_called"] and (run / "lesson_state.json").read_bytes() == before
    # A real receipt is copied once to the existing personal-debrief ledger.
    config = load_config(config_path)
    upstream = Upstream()
    bridge = make_bridge(config, upstream)
    first = ask(bridge, request_id="debrief-log-001", intent="open")
    resumed = ask(bridge, request_id="debrief-log-001", intent="open")
    assert first["debrief_ledger"] == "recorded" and resumed["resumed"] and upstream.calls == 1
    from cohort_lab.debrief import snapshot
    packet = snapshot(run)
    streams = packet["metrics"]["usage_streams"]
    assert len(streams) == 1 and streams[0]["total_tokens"] == 1800 and streams[0]["receipts"] == 1
    assert packet["metrics"]["full_session_inference_tokens"] is None


def test_debrief_uses_current_frozen_evidence_and_json_rubric(tmp_path):
    config = make_config(tmp_path, phase="full", stage_cap=400000)
    choices = {"final_verdict": "Mixed", "recommended_action": "Re-test the partner channel"}
    seed(config, 18, choices=choices)
    sid = "f" * 24
    folder = config.run_dir / "debrief" / sid
    folder.mkdir(parents=True)
    frozen = folder / "evidence-packet.json"
    content = {"schema_version": 2, "snapshot_id": sid, "metrics": {"lab_requests": 22},
               "coverage": {"usage": "UNC measured; native harness unknown"},
               "evidence": [{"id": f"snap:{sid}/ev:1", "kind": "saved_judgment",
                             "text": "Re-test the partner channel", "source": "learner_choices.json"}]}
    frozen.write_text(json.dumps(content), encoding="utf-8")
    (folder.parent / "latest.json").write_text(json.dumps({"snapshot_id": sid, "evidence": str(frozen)}), encoding="utf-8")
    packet = compile_packet(config, "debrief")
    assert "Return JSON only" in packet.instructions
    assert json.loads(packet.text)["evidence"][0]["content"] == content
    assert packet.input_bytes <= 8000
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(content), encoding="utf-8")
    (folder.parent / "latest.json").write_text(json.dumps({"snapshot_id": sid, "evidence": str(outside)}), encoding="utf-8")
    with pytest.raises(BridgeError, match="this workspace"):
        compile_packet(config, "debrief")
