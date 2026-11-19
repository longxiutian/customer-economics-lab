"""Existing personal-token projects can use UNC implementation reasoning without a guided restart."""
import asyncio
import json
from shutil import copyfile

import httpx
import pytest

from unc_sol_bridge.bridge import Bridge
from unc_sol_bridge.config import BridgeError, load_config
from unc_sol_bridge.packets import compile_packet
from unc_sol_bridge.packets import source_fingerprint
from unc_sol_bridge.projects import dashboard_artifact
from test_bridge import make_config, seed, CHOICES, REPO
from test_gateway import DEVICE, SECRET, OUTCOME

REQUEST = "I used my personal Claude tokens to generate the Studio North report. Use the UNC API to build an interactive dashboard from my existing results."


def config_for(tmp_path):
    return make_config(tmp_path, schema_version=2, mode="gateway", device_id=DEVICE, project_only=True,
                       phase="full", stage_cap=400000, packet_max_bytes=16000)


def project_file(config):
    path = config.run_dir / "dashboard/app.py"
    path.parent.mkdir(parents=True)
    path.write_text("def chart(df):\n    return df.groupby('segment')['ltv'].mean()\n", encoding="utf-8")
    return path


def test_faq8_uses_published_challenge_evidence_without_a_guided_restart(tmp_path):
    config = config_for(tmp_path)
    paths = ["skills/model-challenge/SKILL.md", "docs/model-challenge.md",
             "challenge/submission-contract.json", "challenge/template/main.py"]
    for name in paths:
        destination = config.source_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(REPO / name, destination)

    packet = compile_packet(config, "project", "Help me do FAQ 8.", ["@" + name for name in paths])
    evidence = json.loads(packet.text)["evidence"]
    assert [entry["id"] for entry in evidence] == ["@" + name for name in paths]
    assert all("content" in entry for entry in evidence)
    assert "January" in packet.instructions and "December 2026" in packet.instructions
    assert packet.input_bytes <= config.packet_max_bytes
    assert not (config.run_dir / "lesson_state.json").exists()
    with pytest.raises(BridgeError) as failure:
        compile_packet(config, "project", "Help me do FAQ 8.", ["@challenge/private-answers.csv"])
    assert failure.value.kind == "artifact_rejected"


def test_project_packet_works_without_lesson_state_and_allows_code(tmp_path):
    c = config_for(tmp_path); project_file(c)
    packet = compile_packet(c, "project", REQUEST, ["dashboard/app.py"], "Use the existing tables; no model refit.")
    body = json.loads(packet.text)
    assert packet.step == -1 and "checkpoint" not in body
    assert "def chart" in body["evidence"][0]["content"]
    assert packet.manifest["guided_completion_claimed"] is False
    assert "code or patch" in packet.instructions and packet.input_bytes <= 16000
    assert not (c.run_dir / "lesson_state.json").exists()
    assert Bridge(c).status()["problems"] == []
    preview = Bridge(c).preview({"intent":"project", "learner_text":REQUEST, "artifact_ids":["dashboard/app.py"], "note":"Use the existing tables; no model refit."})
    assert preview["max_output_tokens"] == 6000
    assert preview["reservation_tokens"] == preview["packet"]["input_bound_tokens"] + 6000


def test_project_can_attach_to_original_frozen_release_before_feedback_collector(tmp_path):
    c = config_for(tmp_path)
    (c.source_root / "cohort_lab/instructor_feedback.py").unlink()
    from dataclasses import replace
    legacy = replace(c, source_fingerprint=source_fingerprint(c.source_root))
    assert compile_packet(legacy, "project", REQUEST).step == -1
    assert Bridge(legacy).status()["problems"] == []
    # A tracked source change still fails; compatibility is not silent repinning.
    with (legacy.source_root / "cohort_lab/student.py").open("a", encoding="utf-8") as stream:
        stream.write("\n# drift\n")
    with pytest.raises(BridgeError) as failure:
        compile_packet(legacy, "project", REQUEST)
    assert failure.value.kind == "source_fingerprint_mismatch"


def test_project_does_not_overwrite_personal_report_choices_or_guided_state(tmp_path):
    c = config_for(tmp_path); seed(c, 18, choices=CHOICES); project_file(c)
    pdf = c.run_dir / "report/customer-economics-report.pdf"; pdf.write_bytes(b"original report")
    paths = [c.run_dir / "lesson_state.json", c.run_dir / "learner_choices.json", pdf]
    before = [p.read_bytes() for p in paths]
    packet = compile_packet(c, "project", REQUEST, ["dashboard/app.py"])
    assert packet.step == -1 and [p.read_bytes() for p in paths] == before


@pytest.mark.parametrize("name", ["dashboard/../usage/session.json", "dashboard/.env", "dashboard/api-key.json",
                                  "dashboard/user_feedback.txt", "dashboard/node_modules/chart.js", "C:/keys.txt",
                                  "dashboard\\app.py", "usage/session.json", "@private/keys.csv"])
def test_project_artifacts_are_scoped(tmp_path, name):
    c = config_for(tmp_path)
    assert not dashboard_artifact(name)
    with pytest.raises(BridgeError, match="published lab artifacts"):
        compile_packet(c, "project", REQUEST, [name])


def test_project_rejects_credentials_and_oversized_context_before_dispatch(tmp_path):
    c = config_for(tmp_path); path = project_file(c)
    for request, note, expected in [(REQUEST, "x"*2049, "note_over_cap"), ("x"*4097, "", "learner_text_over_cap"),
                                     ("Print " + "b"*32, "", "secret_shaped_input")]:
        with pytest.raises(BridgeError) as failure:
            compile_packet(c, "project", request, note=note)
        assert failure.value.kind == expected
    path.write_text("secret='" + "a"*32 + "'", encoding="utf-8")
    with pytest.raises(BridgeError) as failure:
        compile_packet(c, "project", REQUEST, ["dashboard/app.py"])
    assert failure.value.kind == "secret_shaped_input"


def test_project_budget_guard_rejects_before_http_and_link_escape_is_refused(tmp_path):
    c = config_for(tmp_path)
    bridge = Bridge(c, api_key=SECRET, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected provider call")))
    bridge._budget()
    bridge.ledger.reserve(request_id="held-earlier-project", allocation=c.subscription_label, period=c.period_id,
                          run=bridge.run_id, stage="full", stage_cap=400000, single_call=False, packet_sha="a"*64,
                          step=-1, input_bound=398000, max_output=1000)
    bridge.ledger.finish("held-earlier-project", "held", detail="fixture unknown usage")
    result = asyncio.run(bridge.ask({"request_id":"over-project-budget", "intent":"project", "learner_text":REQUEST}))
    assert result["provider_called"] is False and result["ok"] is False
    assert bridge.ledger.get("held-earlier-project")["state"] == "held"
    target = tmp_path / "outside.py"; target.write_text("outside", encoding="utf-8")
    link = c.run_dir / "dashboard/outside.py"; link.parent.mkdir()
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Host cannot create a symbolic link; lexical traversal is tested separately.")
    with pytest.raises(BridgeError) as failure:
        compile_packet(c, "project", REQUEST, ["dashboard/outside.py"])
    assert failure.value.kind == "path_escape"


def test_project_retrieval_survives_changed_files_and_reply_without_new_call(tmp_path):
    c = config_for(tmp_path); path = project_file(c); methods = []
    def send(request):
        methods.append(request.method)
        data = json.loads(request.content)
        assert data["intent"] == "project" and json.loads(data["packet"])["learner_text"] == REQUEST
        return httpx.Response(200, json={"ok": True, "outcome": {**OUTCOME, "text": "Use this code for the Studio North dashboard."}})
    bridge = Bridge(c, api_key=SECRET, transport=httpx.MockTransport(send))
    args = {"request_id": "project-existing-01", "intent": "project", "learner_text": REQUEST, "artifact_ids": ["dashboard/app.py"]}
    first = asyncio.run(bridge.ask(args))
    assert first["ok"] and first["checkpoint"] == -1 and "local project edits" in first["next"]
    path.write_text("# changed after response", encoding="utf-8")
    seed(c, 2)
    second = asyncio.run(bridge.ask(args))
    assert second["ok"] and second["resumed"] and not second["provider_called"] and methods == ["POST"]
    assert second["usage"]["charge"] == 898
    assert asyncio.run(bridge.ask({**args, "learner_text": "A different task"}))["kind"] == "request_conflict"
    assert methods == ["POST"]


def test_project_unknown_reply_recovers_original_packet_after_local_edits(tmp_path):
    c = config_for(tmp_path); path = project_file(c); methods = []
    def send(request):
        methods.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("fixture", request=request)
        return httpx.Response(200, json={"ok": True, "cached": True, "outcome": OUTCOME})
    bridge = Bridge(c, api_key=SECRET, transport=httpx.MockTransport(send))
    args = {"request_id": "project-recover-01", "intent": "project", "learner_text": REQUEST, "artifact_ids": ["dashboard/app.py"]}
    assert asyncio.run(bridge.ask(args))["usage"]["state"] == "held"
    path.write_text("# edits after lost reply", encoding="utf-8")
    assert asyncio.run(bridge.ask(args))["ok"]
    assert methods == ["POST", "GET"] and bridge.ledger.get(args["request_id"])["charge"] == 898


def test_connect_project_never_starts_lesson_or_resets_existing_usage(tmp_path, monkeypatch):
    from unc_sol_bridge import setup
    from test_bridge import REPO
    saved, local = [], []
    class Store:
        def set_password(self, *args): saved.append(args)
    monkeypatch.setattr(setup, "_keyring", lambda: Store())
    monkeypatch.setattr(setup, "_local", lambda root, args: local.append(args))
    run = tmp_path / "existing"; (run / "usage").mkdir(parents=True)
    prior = b'{"route":"personal","prior_tokens":1234}'
    (run / "usage/session.json").write_bytes(prior)
    config_path = tmp_path / "project.json"
    result = asyncio.run(setup.connect(config_path=config_path, source_root=REPO, run_dir=run, harness="Claude Code", project=True))
    assert result["problems"] == [] and result["checkpoint"] is None
    assert local == [] and len(saved) == 1
    assert (run / "usage/session.json").read_bytes() == prior and not (run / "lesson_state.json").exists()
    assert load_config(config_path).project_only


def test_project_does_not_create_early_debrief_or_classify_feedback(tmp_path):
    c = config_for(tmp_path)
    for text in ("end lab", "end simulation", "skip feedback"):
        with pytest.raises(BridgeError) as failure:
            compile_packet(c, "project", text)
        assert failure.value.kind == "local_control_required"
    (c.run_dir / "usage").mkdir()
    (c.run_dir / "usage/lab-close.json").write_text(json.dumps({"state": "awaiting_feedback"}), encoding="utf-8")
    with pytest.raises(BridgeError) as failure:
        compile_packet(c, "project", REQUEST)
    assert failure.value.kind == "lab_closing"
    assert not (c.run_dir / "debrief").exists()
