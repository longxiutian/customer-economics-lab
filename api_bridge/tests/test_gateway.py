"""Managed-pool transport fixtures. Every HTTP call is intercepted; no live keys or model usage."""
import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from unc_sol_bridge.bridge import Bridge
from unc_sol_bridge.config import BridgeError, load_config
from unc_sol_bridge.gateway import GATEWAY, GatewayClient, secret_hash
from test_bridge import make_config, seed

SECRET = "fixture_device_secret_only_1234567890123456789"
DEVICE = "fixture-device-1234567890"
TEXT = "Start the Studio North guided customer-economics lab in this chat."
OUTCOME = {"kind": "completed", "dispatched": True, "text": "Welcome. Type next step when ready.",
           "input_tokens": 607, "output_tokens": 291, "total_tokens": 898, "model": "gpt-6.1-sol"}


def managed(tmp_path):
    return replace(make_config(tmp_path), mode="gateway", device_id=DEVICE)


def test_gateway_mode_has_no_configurable_endpoint_or_model(tmp_path):
    config = make_config(tmp_path)
    raw = json.loads(config.path.read_text())
    raw.update(schema_version=2, mode="gateway", device_id=DEVICE)
    config.path.write_text(json.dumps(raw))
    assert load_config(config.path).mode == "gateway"
    raw["gateway_url"] = "https://other.invalid"
    config.path.write_text(json.dumps(raw))
    with pytest.raises(BridgeError):
        load_config(config.path)


def test_managed_pool_does_not_inherit_one_subscriptions_ceiling_in_a_future_phase_fixture(tmp_path):
    # Internal continuation fixture only: the shipped subprocess gate still rejects full.
    config = make_config(tmp_path, schema_version=2, mode="gateway", device_id=DEVICE,
                         allocation_cap=50_800_000, phase="full", stage_cap=1_000_000)
    seed(config, 0)
    transport = httpx.MockTransport(lambda _: httpx.Response(200,json={"ok":True,"outcome":OUTCOME}))
    bridge = Bridge(config,api_key=SECRET,transport=transport);bridge._budget()
    bridge.ledger.reserve(request_id="prior-fixture",allocation=config.subscription_label,period=config.period_id,
                          run=bridge.run_id,stage="full",stage_cap=1_000_000,single_call=False,packet_sha="f"*64,
                          step=0,input_bound=399_000,max_output=1_000)
    bridge.ledger.finish("prior-fixture","settled",input_tokens=399_000,output_tokens=1_000,total_tokens=400_000)
    result=asyncio.run(bridge.ask({"request_id":"next-pool-fixture","intent":"open","learner_text":TEXT}))
    assert result["ok"] and result["budget"]["stage_used"] == 400_898
    assert result["budget"]["allocation_cap"] is None  # no invented student pool balance


def test_local_status_preview_do_not_contact_gateway_or_read_secret(tmp_path):
    config = managed(tmp_path); seed(config, 0)
    def forbidden(_):
        raise AssertionError("local status/preview attempted HTTP")
    bridge = Bridge(config, transport=httpx.MockTransport(forbidden))
    assert bridge.status()["route"] == "managed_unc_pool"
    assert bridge.preview({"intent": "open", "learner_text": TEXT})["provider_called"] is False
    assert bridge.status()["budget"]["scope"] == "this_device_only"


def test_managed_opening_then_local_replay_is_one_gateway_dispatch(tmp_path):
    config = managed(tmp_path); seed(config, 0); requests = []
    def send(request):
        requests.append(request)
        assert str(request.url) == GATEWAY + "/ask"
        assert request.headers["X-Sol-Device"] == DEVICE + "." + SECRET
        data = json.loads(request.content)
        assert set(data) == {"request_id", "intent", "instructions", "packet", "learner_text"}
        assert data["learner_text"] == TEXT and TEXT not in data["packet"]
        assert SECRET not in request.content.decode()
        return httpx.Response(200, json={"ok": True, "cached": False, "outcome": OUTCOME})
    bridge = Bridge(config, api_key=SECRET, transport=httpx.MockTransport(send))
    args = {"request_id": "gateway-open-001", "intent": "open", "learner_text": TEXT}
    first = asyncio.run(bridge.ask(args)); second = asyncio.run(bridge.ask(args))
    assert first["ok"] and second["resumed"] and len(requests) == 1
    assert second["usage"]["charge"] == 898 and not second["provider_called"]
    assert SECRET not in json.dumps([first, second])


def test_lost_gateway_reply_recovers_by_get_without_reposting(tmp_path):
    config = managed(tmp_path); seed(config, 0); methods = []
    def send(request):
        methods.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("fixture lost response", request=request)
        assert str(request.url).endswith("/requests/gateway-open-002")
        return httpx.Response(200, json={"ok": True, "cached": True, "outcome": OUTCOME})
    bridge = Bridge(config, api_key=SECRET, transport=httpx.MockTransport(send))
    args = {"request_id": "gateway-open-002", "intent": "open", "learner_text": TEXT}
    first = asyncio.run(bridge.ask(args)); second = asyncio.run(bridge.ask(args)); third = asyncio.run(bridge.ask(args))
    assert first["usage"]["state"] == "held" and not first["ok"]
    assert second["ok"] and second["resumed"] and not second["provider_called"]
    assert third["ok"] and methods == ["POST", "GET"]
    assert bridge.ledger.get(args["request_id"])["charge"] == 898


def test_denials_distinguish_no_call_from_ambiguous_existing_work():
    c = GatewayClient(DEVICE, SECRET)
    assert not c._outcome({"ok": False, "kind": "stage_cap", "charge": "none", "provider_called": False}).dispatched
    assert c._outcome({"ok": False, "kind": "charge_held", "charge": "none", "provider_called": False}).dispatched
    assert c._outcome({"ok": False, "kind": "service_error", "charge": "unknown", "provider_called": True}).dispatched
    assert c._outcome({"ok": True, "outcome": {**OUTCOME, "input_tokens": -1}}).kind == "gateway_unknown"
    assert len(secret_hash(SECRET)) == 43


def test_recovered_usage_enters_personal_debrief_once(tmp_path):
    from test_bridge import REPO
    from unc_sol_bridge.packets import source_fingerprint
    from cohort_lab.debrief import initialize, snapshot
    config = replace(managed(tmp_path), source_root=REPO, source_fingerprint=source_fingerprint(REPO))
    seed(config, 0); initialize(config.run_dir, route="university_mcp", harness="Codex")
    calls = []
    def send(request):
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("lost fixture reply", request=request)
        return httpx.Response(200, json={"ok": True, "cached": True, "outcome": OUTCOME})
    bridge = Bridge(config, api_key=SECRET, transport=httpx.MockTransport(send))
    args = {"request_id": "recover-debrief-001", "intent": "open", "learner_text": TEXT}
    first = asyncio.run(bridge.ask(args)); recovered = asyncio.run(bridge.ask(args)); asyncio.run(bridge.ask(args))
    assert first["debrief_ledger"].startswith("pending") and recovered["debrief_ledger"] == "recorded"
    streams = snapshot(config.run_dir)["metrics"]["usage_streams"]
    assert len(streams) == 1 and streams[0]["receipts"] == 1 and streams[0]["total_tokens"] == 898
    assert calls == ["POST", "GET"]


def test_managed_opening_requires_literal_words_and_binds_them_to_request_id(tmp_path):
    config=managed(tmp_path);seed(config,0);calls=[]
    def send(request):
        calls.append(request)
        return httpx.Response(200,json={"ok":True,"outcome":OUTCOME})
    b=Bridge(config,api_key=SECRET,transport=httpx.MockTransport(send))
    assert asyncio.run(b.ask({"request_id":"literal-test-001","intent":"open"}))["kind"]=="learner_text_required"
    assert asyncio.run(b.ask({"request_id":"literal-test-001","intent":"open","learner_text":TEXT}))["ok"]
    assert asyncio.run(b.ask({"request_id":"literal-test-001","intent":"open","learner_text":"Changed request"}))["kind"]=="request_conflict"
    assert len(calls)==1


def test_connect_is_offline_and_does_not_ask_for_a_code_or_key(tmp_path,monkeypatch):
    from unc_sol_bridge import setup
    from test_bridge import REPO
    from pathlib import Path
    saved=[]
    class Store:
        def set_password(self,*args):saved.append(args)
    monkeypatch.setattr(setup,"_keyring",lambda:Store())
    monkeypatch.setattr(Path,"home",lambda:tmp_path/"owner")
    def forbidden(request):raise AssertionError("connect attempted HTTP")
    path=tmp_path/"config.json"
    result=asyncio.run(setup.connect(config_path=path,source_root=REPO,run_dir=tmp_path/"run",
                                   harness="Claude Code",transport=httpx.MockTransport(forbidden)))
    assert result["connection"]=="prepared_locally" and result["provider_called"] is False
    assert len(saved)==1 and len(saved[0][2])==43
    assert "pairing" not in result and saved[0][2] not in path.read_text()
    assert asyncio.run(setup.connect(config_path=path,source_root=REPO,run_dir=tmp_path/"run",harness="Claude Code"))["connection"]=="prepared_locally"


def test_admission_usage_stays_separate_from_student_sol_allowance(tmp_path):
    from test_bridge import REPO
    from unc_sol_bridge.packets import source_fingerprint
    from cohort_lab.debrief import initialize,snapshot
    config=replace(managed(tmp_path),source_root=REPO,source_fingerprint=source_fingerprint(REPO))
    seed(config,0);initialize(config.run_dir,route="university_mcp",harness="Codex")
    admission={"state":"allowed","model":"jev-latest","checked_at":1234,"usage":{"input_tokens":701,"output_tokens":42}}
    b=Bridge(config,api_key=SECRET,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={"ok":True,"outcome":{**OUTCOME,"admission":admission}})))
    args={"request_id":"split-meter-001","intent":"open","learner_text":TEXT}
    assert asyncio.run(b.ask(args))["debrief_ledger"]=="recorded"
    asyncio.run(b.ask(args));streams=snapshot(config.run_dir)["metrics"]["usage_streams"]
    assert {s["scope"]:s["total_tokens"] for s in streams}=={"admission":743,"university_mcp":898}
    assert b.ledger.get(args["request_id"])["charge"]==898


def test_released_opening_matches_the_frozen_gateway_packet(tmp_path):
    from test_bridge import REPO
    from unc_sol_bridge.packets import compile_packet
    config=make_config(tmp_path);seed(config,0)
    actual=compile_packet(config,"open")
    frozen=json.loads((REPO/"api_bridge/admission/opening.json").read_text())
    assert frozen=={"instructions":actual.instructions,"packet":actual.text,"input_bytes":actual.input_bytes}
