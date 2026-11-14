"""Offline adversarial tests. Nothing here contacts a provider; HTTP is an in-process mock with a call counter."""
import asyncio
import hashlib
import json
import shutil
import sqlite3
import sys
import threading
import time
import tomllib
from pathlib import Path

import httpx
import pytest

from unc_sol_bridge import client
from unc_sol_bridge.bridge import Bridge
from unc_sol_bridge.budget import BudgetBlocked, Ledger
from unc_sol_bridge.cli import install, render
from unc_sol_bridge.config import BridgeError, load_config
from unc_sol_bridge.packets import EXTRA_ARTIFACTS, PacketError, compile_packet, load_lessons, source_fingerprint

REPO = Path(__file__).resolve().parents[2]
URL = "https://sol.invalid/openai/v1/responses"  # reserved TLD: unreachable even if the mock were bypassed
KEY = "unit-test-key-0123456789abcdef"  # fake
PERIOD = time.strftime("%Y-%m", time.gmtime())
LESSONS = load_lessons(REPO)
SOURCES = sorted({"cohort_lab/student.py", "hosting/student_debrief.py"} | {name[1:] for lesson in LESSONS for name in lesson.files if name.startswith("@")})
CHOICES = {"final_verdict": "Mixed: retention improves, payback does not.", "recommended_action": "Hold partner spend until the next holdout."}
REPLY = "Welcome to Studio North.\n\nWhat would you like to ask before typing next step?"
QUESTION = "Why could joining transaction and activity rows multiply revenue?"
PILOT = {"phase": "pilot", "stage_cap": 100_000}


def make_config(tmp_path, **overrides):
    folders = {name: (tmp_path / name).resolve() for name in ("src", "run", "data", "state")}
    for folder in folders.values():
        folder.mkdir(exist_ok=True)
    for name in SOURCES:  # a private copy of the real lesson sources, so tests may mutate them safely
        target = folders["src"] / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, target)
    raw = {"schema_version": 1, "source_root": str(folders["src"]), "data_dir": str(folders["data"]), "run_dir": str(folders["run"]),
           "state_dir": str(folders["state"]), "subscription_label": "unit-test-allocation", "period_id": PERIOD,
           "baseline_tokens": 0, "baseline_source": "unit fixture, unused allocation", "allocation_cap": 400_000,
           "phase": "startup", "stage_cap": 10_000, "source_fingerprint": source_fingerprint(folders["src"]),
           "credential_ref": {"kind": "env", "name": "UNC_SOL_TEST_KEY"}}
    (tmp_path / "bridge.json").write_text(json.dumps({**raw, **overrides}), encoding="utf-8")
    return load_config(tmp_path / "bridge.json")


def fixture_bytes(name):
    suffix = Path(name).suffix
    if suffix == ".csv":
        rows = "".join(f"2024-{1 + i % 12:02d},{i % 12},{i / 300:.4f},member-{i:04d}\n" for i in range(300))
        return ("cohort_month,age_month,retained_share,member_id\n" + rows).encode()
    if suffix == ".json":
        return json.dumps({"version": 1, "items": [{"k": i, "note": "x" * 40} for i in range(200)]}).encode()
    if suffix == ".md":
        return "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(40)).encode()
    if suffix == ".tex":
        return ("\\section{Recommendation}\n" + "body " * 9000 + "\n\\section{Appendix}\n").encode()
    return b"\x89PNG\r\n\x1a\n unit fixture, never transmitted"


def seed(config, step, result=None, choices=None, **state):
    """Write what the lab harness would have saved at this checkpoint: its state file and the lesson's artifacts."""
    for name in [*LESSONS[step].files, *EXTRA_ARTIFACTS.get(step, ())]:
        if name.startswith("@") or name == "learner_choices.json":
            continue
        path = config.data_dir / name[11:] if name.startswith("tables:raw/") else config.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fixture_bytes(name))
    if choices is not None:
        (config.run_dir / "learner_choices.json").write_text(json.dumps(choices), encoding="utf-8")
    document = {"schema_version": 1, "completed_step": step, "implementation": {"cohort_lab/student.py": "f" * 64},
                "inputs": {"people.csv": "e" * 64}, "messages": [], "invalidations": [],
                "results": {str(step): {"files": []} if result is None else result}, **state}
    (config.run_dir / "lesson_state.json").write_text(json.dumps(document), encoding="utf-8")


def harness_result(config, step):
    result = {"files": []}
    if step == 1:
        result["readiness"] = {"python": "ok", "duckdb": "ok", "dataset": "verified"}
    if step >= 6:
        result["data_context"] = {"dataset_version": "unit", "observed_cutoff_exclusive": "2026-01-01", "currency": "USD"}
    if step == 6:
        trace = config.run_dir / "queries" / "age2.csv"
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.write_bytes(fixture_bytes(trace.name))
        result["cell_trace"] = {"sql": "SELECT cohort_month, age_month FROM customer_month WHERE age_month = 2", "artifacts": [str(trace)]}
    if step == 18:
        result["compiled_pdf"] = True
    return result


def answer(text=REPLY, **changes):
    body = {"id": "resp_unit_0001", "object": "response", "status": "completed", "model": "gpt-6.1-sol",
            "output": [{"type": "reasoning", "summary": []},
                       {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 1_100, "output_tokens": 700, "total_tokens": 1_800,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 400}}}
    return {key: value for key, value in {**body, **changes}.items() if value is not None}


class Upstream:
    """In-process stand-in for the provider. Records every dispatch so tests can prove none was added or replayed."""

    def __init__(self, reply=None):
        self.reply, self.requests = reply, []

    def __call__(self, request):
        self.requests.append(request)
        reply = self.reply(request) if callable(self.reply) else self.reply
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=answer() if reply is None else reply)

    @property
    def calls(self):
        return len(self.requests)

    def sent(self, index=-1):
        return json.loads(self.requests[index].content)


def make_bridge(config, upstream):
    return Bridge(config, api_key=KEY, transport=httpx.MockTransport(upstream), url=URL)


def ask(bridge, **fields):
    return asyncio.run(bridge.ask(fields))


def refused(config, *args, **kwargs):
    with pytest.raises(PacketError) as caught:
        compile_packet(config, *args, **kwargs)
    return caught.value.kind


def blocked(action, *args, **kwargs):
    with pytest.raises(BudgetBlocked) as caught:
        action(*args, **kwargs)
    return caught.value.kind


def hold(ledger, request_id, *, run="run-a", stage="pilot", stage_cap=400_000, single_call=False, input_bound=5_200):
    return ledger.reserve(request_id=request_id, allocation="alloc", period=PERIOD, run=run, stage=stage, stage_cap=stage_cap,
                          single_call=single_call, packet_sha="0" * 64, step=0, input_bound=input_bound, max_output=3_000)


def leaked(config, *payloads):
    files = [path for folder in (config.run_dir, config.state_dir) for path in folder.rglob("*") if path.is_file()]
    return KEY in json.dumps(payloads) or any(KEY.encode() in path.read_bytes() for path in files)


# ---------------------------------------------------------------- fixed release facts

def test_release_pin_and_fixed_request_shape():
    # Fails until the release pin is the endpoint already proven by the instructor MCP. It is never configurable.
    assert client.RESPONSES_URL == "https://azureaiapi.cloud.unc.edu/openai/v1/responses"
    assert client.build_request("contract", "packet") == {
        "model": "gpt-6.1-sol", "instructions": "contract", "input": "packet", "max_output_tokens": 3000,
        "reasoning": {"effort": "medium"}, "store": False, "stream": False}


def test_server_builds_without_config_key_or_upstream(tmp_path):
    from unc_sol_bridge.server import build_server
    assert build_server(tmp_path / "absent.json") is not None


def test_lessons_are_read_as_literals_without_importing_the_lab():
    assert [len(LESSONS), LESSONS[0].title, LESSONS[0].core_stage, LESSONS[18].core_stage] == [19, "Welcome to Studio North", -1, 7]
    assert LESSONS[0].files == ("@docs/business_brief.md",) and "cohort_lab.student" not in sys.modules


@pytest.mark.parametrize("override", [
    {"endpoint": "https://example.invalid/v1/responses"}, {"model": "gpt-6.1-luna"}, {"api_key": KEY},
    {"credential_ref": {"kind": "env", "name": "UNC_SOL_TEST_KEY", "value": KEY}},
    {"credential_ref": {"kind": "file", "path": "/tmp/key.txt"}},
    {"subscription_label": "sk-live0123456789abcdef"}, {"allocation_cap": 400_001}, {"stage_cap": 10_001},
    {"packet_max_bytes": 5_001}, {"baseline_tokens": -1}, {"baseline_source": "guess"}, {"period_id": "2999-01"},
])
def test_config_cannot_carry_endpoint_model_key_or_looser_caps(tmp_path, override):
    with pytest.raises(BridgeError) as caught:
        make_config(tmp_path, **override)
    assert caught.value.kind == "config_invalid"


# ---------------------------------------------------------------- compact packets

def test_opening_packet_is_compact_reviewed_and_compiled_from_saved_state(tmp_path):
    config = make_config(tmp_path)
    seed(config, 0)
    packet = compile_packet(config, "open")
    body = json.loads(packet.text)
    assert config.packet_max_bytes == 5_000 and packet.step == 0
    assert packet.input_bytes == len(packet.instructions.encode()) + len(packet.text.encode()) <= 5_000
    assert packet.input_bound == packet.input_bytes + 200 and packet.input_bound + 3_000 <= config.stage_cap
    assert set(body) == {"checkpoint", "intent", "objective", "check", "progress", "judgments", "evidence"}
    assert body["checkpoint"] == {"step": 0, "last": 18, "title": "Welcome to Studio North"}
    assert (body["objective"], body["check"], body["judgments"]) == (LESSONS[0].objective, LESSONS[0].check, "none saved")
    (brief,) = body["evidence"]
    assert brief["id"] == "@docs/business_brief.md" and brief["omitted"].startswith("reviewed excerpt: 4 of ")
    assert "Are we moving in the right direction as a company?" in brief["content"] and "eight separate exports" in brief["content"]
    assert "Comparison rules" not in packet.text and "12-month horizon" not in packet.text  # deferred, and recorded as omitted
    (source,) = packet.manifest["sources"]
    path = config.source_root / "docs" / "business_brief.md"
    assert (source["sha256"], source["source_bytes"]) == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)
    assert packet.manifest["source_fingerprint"] == config.source_fingerprint
    assert compile_packet(config, "open").sha256 == packet.sha256  # the same saved state compiles the same packet


def test_all_19_checkpoints_compile_bounded_packets_from_harness_fixtures(tmp_path):
    config = make_config(tmp_path, **PILOT)
    assert config.packet_max_bytes == 8_000
    seen = set()
    for step, lesson in enumerate(LESSONS):
        seed(config, step, harness_result(config, step), choices=CHOICES if step == 18 else None)
        packet = compile_packet(config, "teach")
        body = json.loads(packet.text)
        evidence = body.get("evidence", [])
        expected = ([name for name in lesson.files if name != "learner_choices.json"] + list(EXTRA_ARTIFACTS.get(step, ()))
                    + (["queries/age2.csv"] if step == 6 else []))
        assert packet.step == body["checkpoint"]["step"] == step
        assert (body["objective"], body["check"]) == (lesson.objective, lesson.check)
        assert packet.input_bytes <= config.packet_max_bytes
        assert [entry["id"] for entry in evidence] == expected
        assert all("content" in entry or entry.get("omitted") for entry in evidence)  # nothing is dropped silently
        assert [source["id"] for source in packet.manifest["sources"]] == expected
        assert all(len(source["sha256"]) == 64 for source in packet.manifest["sources"])
        assert ("harness_context" in body) == (step == 1 or step >= 6)
        assert body["judgments"] == (CHOICES if step == 18 else "none saved")
        seen.add(packet.sha256)
    assert len(seen) == 19


def test_selected_evidence_is_real_rows_with_recorded_omission(tmp_path):
    config = make_config(tmp_path, **PILOT)
    seed(config, 9)
    name = "tables/segmentation_objective.csv"
    path = config.run_dir / name
    packet = compile_packet(config, "teach", artifact_ids=[name])
    (entry,) = json.loads(packet.text)["evidence"]
    assert entry["id"] == name and entry["omitted"] == "rows 7-300 omitted"
    assert entry["content"]["columns"] == ["cohort_month", "age_month", "retained_share", "member_id"]
    assert entry["content"]["row_count"] == 300 and len(entry["content"]["rows"]) == 6
    assert entry["content"]["rows"][0] == ["2024-01", "0", "0.0000", "member-0000"] and "member-0299" not in packet.text
    (source,) = packet.manifest["sources"]
    assert (source["id"], source["sha256"], source["omitted"]) == (name, hashlib.sha256(path.read_bytes()).hexdigest(), "rows 7-300 omitted")
    assert 0 < source["included_bytes"] < source["source_bytes"] == path.stat().st_size
    path.write_text("cohort_month,retained_share\n" + "".join(f"2024-{m:02d},0.{90 - m}\n" for m in range(1, 13)), encoding="utf-8")
    (whole,) = json.loads(compile_packet(config, "teach", artifact_ids=[name]).text)["evidence"]
    assert len(whole["content"]["rows"]) == 12 and "omitted" not in whole  # a small table is not starved


@pytest.mark.parametrize("step, intent, fields, kind", [
    (5, "question", {"learner_text": "é" * 601}, "learner_text_over_cap"),
    (5, "question", {}, "learner_text_required"),
    (5, "critique", {"learner_text": "   "}, "learner_text_required"),
    (5, "teach", {"learner_text": "next step"}, "learner_text_not_allowed"),
    (5, "open", {}, "intent_not_available"),
    (5, "debrief", {}, "intent_not_available"),
    (5, "summarize", {}, "invalid_arguments"),
    (5, "troubleshoot", {"note": "n" * 281}, "note_over_cap"),
    (5, "teach", {"artifact_ids": ["lesson_state.json"]}, "artifact_rejected"),
    (5, "teach", {"artifact_ids": ["../state/budget.sqlite3"]}, "artifact_rejected"),
    (5, "teach", {"artifact_ids": ["@cohort_lab/student.py"]}, "artifact_rejected"),
    (18, "teach", {}, "judgment_missing"),
])
def test_packet_rules_reject_instead_of_rewriting(tmp_path, step, intent, fields, kind):
    config = make_config(tmp_path, **PILOT)
    seed(config, step)
    assert refused(config, intent, **fields) == kind


def test_judgments_and_learner_text_are_literal_or_absent(tmp_path):
    config = make_config(tmp_path, **PILOT)
    seed(config, 18, choices={**CHOICES, "final_verdict": "   "})
    assert refused(config, "teach") == "judgment_missing"
    seed(config, 18, choices={**CHOICES, "segmentation_rationale": "x" * 2_400})
    assert refused(config, "teach") == "judgments_over_cap"
    seed(config, 18, choices=CHOICES)
    assert json.loads(compile_packet(config, "teach").text)["judgments"] == CHOICES
    text = "é" * 600  # exactly at the 1200-byte cap
    body = json.loads(compile_packet(config, "critique", text, note="Learner asked for a candid review.").text)
    assert (body["learner_text"], body["host_note"]) == (text, "Learner asked for a candid review.")
    assert refused(config, "debrief") == "artifact_missing"
    (config.run_dir / "debrief").mkdir()
    sid = "a" * 24
    frozen = config.run_dir / "debrief" / sid / "evidence-packet.json"
    frozen.parent.mkdir()
    contents = {"snapshot_id": sid, "evidence": [{"id": f"snap:{sid}/ev:1", "text": "traced the age-2 cell"}]}
    frozen.write_text(json.dumps(contents), encoding="utf-8")
    (config.run_dir / "debrief" / "latest.json").write_text(json.dumps({"snapshot_id": sid, "evidence": str(frozen)}), encoding="utf-8")
    evidence = json.loads(compile_packet(config, "debrief").text)["evidence"]
    assert evidence == [{"id": f"debrief/{sid}/evidence-packet.json", "content": contents}]


def test_source_changes_fail_closed(tmp_path):
    config = make_config(tmp_path)
    seed(config, 0)
    brief = config.source_root / "docs" / "business_brief.md"
    original = brief.read_text(encoding="utf-8")
    brief.write_text(original + "\n\nAn unreviewed paragraph.\n", encoding="utf-8")
    assert refused(config, "open") == "source_fingerprint_mismatch"
    brief.write_text(original.replace("Management is reviewing", "Leadership is reviewing"), encoding="utf-8")
    assert refused(make_config(tmp_path), "open") == "source_drift"  # re-pinned, but a reviewed anchor is gone


def test_bridge_never_starts_or_repairs_the_lesson(tmp_path):
    config = make_config(tmp_path)
    upstream = Upstream()
    result = ask(make_bridge(config, upstream), request_id="fresh-0001", intent="open")
    assert (result["kind"], result["provider_called"]) == ("lesson_not_started", False)
    assert upstream.calls == 0 and list(config.run_dir.iterdir()) == []  # a fresh run folder stays fresh
    (config.run_dir / "lesson_state.json").write_text('{"completed_step": 19, "results": {}}', encoding="utf-8")
    assert refused(config, "teach") == "lesson_state_invalid"
    (config.run_dir / "lesson_state.json").write_text("{not json", encoding="utf-8")
    assert refused(config, "teach") == "lesson_state_invalid"


# ---------------------------------------------------------------- offline budget ledger

def test_guard_counts_baseline_settled_and_outstanding_before_any_dispatch(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    assert blocked(hold, ledger, "req-00000") == "period_unopened"
    ledger.open_period("alloc", PERIOD, 400_000, 390_000, "portal reading, unit fixture")
    assert hold(ledger, "req-00001") == 8_200
    assert blocked(hold, ledger, "req-00001", run="run-b") == "duplicate_request_id"
    assert blocked(hold, ledger, "req-00002") == "call_in_flight"  # one in flight per run
    assert blocked(hold, ledger, "req-00002", run="run-b") == "allocation_cap"  # 390000 + 8200 outstanding + 8200 > cap
    ledger.finish("req-00001", "settled", input_tokens=4_000, output_tokens=1_000, total_tokens=5_000)
    assert ledger.snapshot("alloc", PERIOD, "pilot")["remaining"] == 5_000
    assert hold(ledger, "req-00003", input_bound=1_500) == 4_500
    ledger.finish("req-00003", "held", detail="timeout")  # dispatched with unknown usage: stays counted
    view = ledger.snapshot("alloc", PERIOD, "pilot")
    assert (view["settled"], view["outstanding"], view["remaining"]) == (5_000, 4_500, 500)
    assert blocked(hold, ledger, "req-00004", input_bound=10, run="run-b") == "allocation_cap"


def test_stage_cap_is_inclusive_and_startup_permits_one_dispatched_call(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.open_period("alloc", PERIOD, 400_000, 0, "unit fixture")
    startup = {"stage": "startup", "stage_cap": 10_000}
    hold(ledger, "open-00001", single_call=True, **startup)
    ledger.finish("open-00001", "released", detail="not_dispatched")  # never left this machine
    assert ledger.snapshot("alloc", PERIOD, "startup")["stage_used"] == 0
    hold(ledger, "open-00002", single_call=True, **startup)
    ledger.finish("open-00002", "settled", input_tokens=1_100, output_tokens=700, total_tokens=1_800)
    assert blocked(hold, ledger, "open-00003", single_call=True, **startup) == "startup_call_already_used"
    assert blocked(hold, ledger, "open-00003", input_bound=5_201, **startup) == "stage_cap"  # 1800 + 8201 > 10000
    assert hold(ledger, "open-00003", **startup) == 8_200  # 1800 + 8200 == 10000


def test_baseline_is_never_lowered_and_periods_never_regress(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.open_period("alloc", PERIOD, 400_000, 1_000, "portal reading one")
    assert blocked(ledger.open_period, "alloc", PERIOD, 400_000, 0, "wishful reset") == "baseline_reset_refused"
    ledger.open_period("alloc", PERIOD, 400_000, 2_500, "portal reading two")
    view = ledger.snapshot("alloc", PERIOD, "pilot")
    assert (view["baseline"], view["baseline_source"]) == (2_500, "portal reading two")
    assert blocked(ledger.open_period, "alloc", "2000-01", 400_000, 0, "an older month") == "period_regressed"


def test_orphaned_in_flight_call_stays_held(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.open_period("alloc", PERIOD, 400_000, 0, "unit fixture")
    hold(ledger, "req-00001")
    db = sqlite3.connect(tmp_path / "ledger.sqlite3")
    db.execute("UPDATE calls SET created = created - 3600")  # the process that dispatched it died an hour ago
    db.commit()
    db.close()
    assert blocked(hold, ledger, "req-00002") == "charge_held"
    assert ledger.get("req-00001")["state"] == "held"
    assert ledger.snapshot("alloc", PERIOD, "pilot")["outstanding"] == 8_200


def test_concurrent_reservations_cannot_both_pass_the_guard(tmp_path):
    path, results = tmp_path / "ledger.sqlite3", []
    Ledger(path).open_period("alloc", PERIOD, 10_000, 0, "unit fixture")

    def worker(number):
        try:
            hold(Ledger(path), f"req-{number:05d}", run=f"run-{number}")
            results.append("reserved")
        except BudgetBlocked as error:
            results.append(error.kind)

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["allocation_cap"] * 5 + ["reserved"]


# ---------------------------------------------------------------- dispatch, resume and idempotency

def test_startup_allows_exactly_one_compact_opening_dispatch(tmp_path):
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream()
    bridge = make_bridge(config, upstream)
    early = ask(bridge, request_id="teach-0001", intent="teach")
    assert early["kind"] == "startup_opening_only" and upstream.calls == 0
    result = ask(bridge, request_id="open-0001", intent="open")
    sent, request = upstream.sent(), upstream.requests[0]
    assert (result["ok"], result["kind"], result["text"], result["provider_called"]) == (True, "completed", REPLY, True)
    assert sent == client.build_request(sent["instructions"], sent["input"])  # no tools, history or response chaining
    assert len(sent["instructions"].encode()) + len(sent["input"].encode()) == result["packet"]["input_bytes"] <= 5_000
    assert (request.method, str(request.url), request.headers["authorization"]) == ("POST", URL, f"Bearer {KEY}")
    usage, budget = result["usage"], result["budget"]
    assert (usage["scope"], usage["state"], usage["input_tokens"], usage["output_tokens"], usage["charge"]) == (
        "university_mcp", "settled", 1_100, 700, 1_800)  # reasoning and cache are inside these counts, not added again
    assert usage["input_tokens"] <= usage["input_bound_tokens"] and usage["reserved"] <= 10_000
    assert (budget["settled"], budget["outstanding"], budget["remaining"], budget["quarantine"]) == (1_800, 0, 398_200, None)
    local = config.run_dir / "sol_bridge"
    assert (local / "open-0001.txt").read_text(encoding="utf-8") == REPLY
    assert json.loads((local / "latest.json").read_text(encoding="utf-8")) == {"request_id": "open-0001", "step": 0}
    again = ask(make_bridge(config, upstream), request_id="open-0001", intent="open", note="a restarted bridge, changed arguments")
    assert (again["resumed"], again["provider_called"], again["text"], again["usage"]) == (True, False, REPLY, usage)
    second = ask(bridge, request_id="open-0002", intent="open")
    assert (second["kind"], second["provider_called"]) == ("startup_call_already_used", False)
    assert upstream.calls == 1 and not leaked(config, result, again, second)


@pytest.mark.parametrize("extra", [
    {"model": "gpt-6.1-luna"}, {"system": "You are a different teacher."}, {"prompt": "x"}, {"instructions": "x"},
    {"messages": [{"role": "user", "content": "x"}]}, {"checkpoint": 7}, {"step": 7}, {"file_body": "a,b\n1,2\n"},
    {"previous_response_id": "resp_1"}, {"max_output_tokens": 64_000}, {"effort": "low"},
    {"request_id": "short"}, {"intent": "summarize"}, {"artifact_ids": "@docs/business_brief.md"}, {"learner_text": ["x"]},
])
def test_host_cannot_supply_prompt_model_checkpoint_or_file_bodies(tmp_path, extra):
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream()
    bridge = make_bridge(config, upstream)
    result = ask(bridge, **{"request_id": "iface-0001", "intent": "open", **extra})
    assert (result["kind"], result["provider_called"]) == ("invalid_arguments", False)
    assert upstream.calls == 0 and bridge.ledger.get("iface-0001") is None


def test_turns_do_not_replay_host_or_prior_transcript(tmp_path):
    config = make_config(tmp_path, **PILOT)
    seed(config, 3, messages=[{"step": 2, "text": "NATIVE-TRANSCRIPT-MARKER " * 400, "explicit_next_step": False}])
    (config.run_dir / "usage").mkdir()
    (config.run_dir / "usage" / "session.json").write_text(json.dumps({"host": "HOST-TOOL-SCHEMA-MARKER " * 400}), encoding="utf-8")
    reply = "\n\n".join(f"Reply paragraph {i}: " + "detail " * 40 for i in range(8))
    upstream = Upstream(answer(reply, model="gpt-6.1-sol-2026-10-01"))  # a dated snapshot of the same model is accepted
    bridge = make_bridge(config, upstream)
    first = ask(bridge, request_id="turn-0001", intent="teach")
    second = ask(bridge, request_id="turn-0002", intent="question", learner_text=QUESTION)
    third = ask(bridge, request_id="turn-0003", intent="question", learner_text=QUESTION)
    assert [turn["ok"] for turn in (first, second, third)] == [True, True, True] and upstream.calls == 3
    assert first["model"] == "gpt-6.1-sol-2026-10-01"
    for index in range(3):
        assert set(upstream.sent(index)) == set(client.build_request("", ""))
        assert "MARKER" not in upstream.requests[index].content.decode("utf-8")
    assert "previous_reply" not in json.loads(upstream.sent(0)["input"])
    body = json.loads(upstream.sent(1)["input"])
    assert set(body) == {"checkpoint", "intent", "objective", "check", "progress", "judgments", "learner_text", "previous_reply", "evidence"}
    assert body["learner_text"] == QUESTION and len(body["previous_reply"].encode()) <= 1_200
    assert "Reply paragraph 0" in body["previous_reply"] and "Reply paragraph 7" not in upstream.sent(1)["input"]
    assert third["packet"]["input_bytes"] == second["packet"]["input_bytes"] <= config.packet_max_bytes  # no growth per turn


# ---------------------------------------------------------------- HTTP faults

FAULTS = [
    ("auth_rejected", lambda: httpx.Response(401, json={"error": {"code": f"invalid_api_key {KEY}"}}), "held"),
    ("quota_rejected", lambda: httpx.Response(429, json={"error": {"type": "insufficient_quota"}}), "held"),
    ("upstream_error", lambda: httpx.Response(503, text="unavailable"), "held"),
    ("redirect_refused", lambda: httpx.Response(302, headers={"Location": "https://elsewhere.invalid/v1/responses"}), "held"),
    ("invalid_response", lambda: httpx.Response(200, text="<html>gateway</html>"), "held"),
    ("response_too_large", lambda: httpx.Response(200, content=b"x" * 300_000), "held"),
    ("usage_missing", lambda: answer(usage=None), "held"),
    ("timeout", lambda: httpx.ReadTimeout("no reply"), "held"),
    ("model_mismatch", lambda: answer(model="gpt-6.1-luna"), "settled"),
    ("incomplete", lambda: answer(status="incomplete", incomplete_details={"reason": "max_output_tokens"}), "settled"),
    ("empty_output", lambda: answer(""), "settled"),
    ("not_dispatched", lambda: httpx.ConnectError("refused"), "released"),
]


@pytest.mark.parametrize("kind, make, state", FAULTS, ids=[fault[0] for fault in FAULTS])
def test_upstream_faults_are_never_retried_and_never_free_a_dispatched_reservation(tmp_path, kind, make, state):
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream(make())
    bridge = make_bridge(config, upstream)
    result = ask(bridge, request_id="fault-0001", intent="open")
    row, budget = bridge.ledger.get("fault-0001"), result["budget"]
    assert (result["ok"], result["kind"]) == (False, kind) and "text" not in result
    assert "not retry" in result["next"] and upstream.calls == 1
    assert row["state"] == state and result["provider_called"] is (state != "released")
    assert (budget["settled"], budget["outstanding"]) == {"held": (0, row["reserved"]), "settled": (1_800, 0), "released": (0, 0)}[state]
    again = ask(bridge, request_id="fault-0001", intent="open")
    assert (again["kind"], again["resumed"], again["provider_called"]) == (kind, True, False) and upstream.calls == 1
    if state != "released":  # no additional test after an auth, quota or any other dispatched failure
        other = ask(bridge, request_id="fault-0002", intent="open")
        assert other["kind"] == ("quarantined" if kind == "model_mismatch" else "startup_call_already_used")
        assert upstream.calls == 1
    assert not leaked(config, result, again)


def test_usage_above_the_reserved_bound_quarantines_the_allocation(tmp_path):
    config = make_config(tmp_path, **PILOT)
    seed(config, 0)
    upstream = Upstream(answer(usage={"input_tokens": 9_500, "output_tokens": 700, "total_tokens": 9_000}))
    bridge = make_bridge(config, upstream)
    first = ask(bridge, request_id="bound-0001", intent="teach")
    assert first["usage"]["charge"] == 10_200  # never below input + output, whatever total the gateway reports
    assert "exceeded" in first["budget"]["quarantine"]
    second = ask(bridge, request_id="bound-0002", intent="teach")
    assert second["kind"] == "quarantined" and upstream.calls == 1


def test_reply_for_a_checkpoint_that_moved_is_saved_but_not_delivered(tmp_path):
    config = make_config(tmp_path)
    seed(config, 0)

    def advance_then_answer(request):
        seed(config, 1)  # the learner typed next step while Sol was answering
        return answer()

    upstream = Upstream(advance_then_answer)
    bridge = make_bridge(config, upstream)
    result = ask(bridge, request_id="stale-0001", intent="open")
    assert (result["ok"], result["kind"], result["checkpoint"]) == (False, "stale_checkpoint", 0) and "text" not in result
    assert result["usage"]["charge"] == 1_800
    local = config.run_dir / "sol_bridge"
    assert (local / "stale-0001.txt").is_file() and not (local / "latest.json").exists()
    assert ask(bridge, request_id="stale-0001", intent="open")["kind"] == "stale_checkpoint" and upstream.calls == 1


def test_cancellation_after_dispatch_holds_the_reservation(tmp_path):
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream(asyncio.CancelledError())
    bridge = make_bridge(config, upstream)
    with pytest.raises(asyncio.CancelledError):
        ask(bridge, request_id="cancel-0001", intent="open")
    row = bridge.ledger.get("cancel-0001")
    assert (row["state"], row["charge"]) == ("held", 0) and "charge unknown" in row["detail"]
    again = ask(bridge, request_id="cancel-0001", intent="open")
    assert (again["kind"], again["provider_called"], again["ledger_state"]) == ("charge_held", False, "held")
    assert upstream.calls == 1 and bridge.status()["budget"]["outstanding"] == row["reserved"]


# ---------------------------------------------------------------- zero-cost paths

def test_missing_credential_fails_before_any_reservation(tmp_path, monkeypatch):
    monkeypatch.delenv("UNC_SOL_TEST_KEY", raising=False)
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream()
    bridge = Bridge(config, transport=httpx.MockTransport(upstream), url=URL)
    result = ask(bridge, request_id="nokey-0001", intent="open")
    assert (result["kind"], result["provider_called"]) == ("credential_unavailable", False)
    assert upstream.calls == 0 and bridge.ledger.get("nokey-0001") is None
    monkeypatch.setenv("UNC_SOL_TEST_KEY", KEY)  # supplied by reference from the client environment
    assert ask(bridge, request_id="nokey-0001", intent="open")["ok"]
    assert upstream.requests[0].headers["authorization"] == f"Bearer {KEY}" and not leaked(config, result)


@pytest.mark.parametrize("url", ["", "http://sol.invalid/openai/v1/responses"])
def test_unpinned_or_insecure_endpoint_fails_closed(tmp_path, url):
    config = make_config(tmp_path)
    seed(config, 0)
    upstream = Upstream()
    bridge = Bridge(config, api_key=KEY, transport=httpx.MockTransport(upstream), url=url)
    result = ask(bridge, request_id="unpin-0001", intent="open")
    assert result["kind"] == "endpoint_unpinned" and bridge.status()["endpoint_pinned"] is False
    assert upstream.calls == 0 and bridge.ledger.get("unpin-0001") is None


def test_status_preview_and_receipt_never_call_the_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("UNC_SOL_TEST_KEY", raising=False)
    config = make_config(tmp_path)
    upstream = Upstream()
    bridge = make_bridge(config, upstream)
    cold = bridge.status()
    assert cold["ok"] and [problem["kind"] for problem in cold["problems"]] == ["lesson_not_started"]
    assert list(config.run_dir.iterdir()) == []
    seed(config, 0)
    status = bridge.status()
    assert status["problems"] == [] and status["checkpoint"] == {"step": 0, "last": 18, "title": "Welcome to Studio North"}
    assert (status["model"], status["effort"], status["max_output_tokens"], status["phase"]) == ("gpt-6.1-sol", "medium", 3000, "startup")
    assert status["credential"] == {"kind": "env", "name": "UNC_SOL_TEST_KEY", "present": False}
    assert (status["budget"]["remaining"], status["budget"]["baseline_source"]) == (400_000, "unit fixture, unused allocation")
    preview = bridge.preview({"intent": "open"})
    assert preview["fits_token_caps"] and preview["reservation_tokens"] == preview["packet"]["input_bound_tokens"] + 3_000 <= 10_000
    assert upstream.calls == 0
    assert ask(bridge, request_id="open-0001", intent="open")["ok"]
    receipt = bridge.receipt({"request_id": "open-0001"})
    assert (receipt["ledger"]["state"], receipt["receipt"]["usage"]["charge"]) == ("settled", 1_800)
    assert receipt["receipt"]["packet"]["sha256"] == preview["packet"]["sha256"]
    with pytest.raises(BridgeError) as caught:
        bridge.receipt({"request_id": "never-0001"})
    assert caught.value.kind == "unknown_request" and upstream.calls == 1 and not leaked(config, status, preview, receipt)


def test_budget_block_happens_before_http_and_a_baseline_cannot_be_reset(tmp_path):
    config = make_config(tmp_path, baseline_tokens=398_000, baseline_source="operator read the portal, unit fixture")
    seed(config, 0)
    upstream = Upstream()
    bridge = make_bridge(config, upstream)
    assert bridge.preview({"intent": "open"})["fits_token_caps"] is False
    result = ask(bridge, request_id="block-0001", intent="open")
    assert (result["kind"], result["provider_called"], result["charge"]) == ("allocation_cap", False, "none")
    assert result["remaining"] == 2_000 < result["needed"]
    assert upstream.calls == 0 and bridge.ledger.get("block-0001") is None
    reset = ask(make_bridge(make_config(tmp_path, baseline_tokens=0), upstream), request_id="block-0002", intent="open")
    assert (reset["kind"], reset["recorded_baseline"]) == ("baseline_reset_refused", 398_000) and upstream.calls == 0


# ---------------------------------------------------------------- client definitions

def test_client_definitions_are_optional_reference_only_and_never_overwrite(tmp_path):
    config = make_config(tmp_path)
    codex = tomllib.loads(render("codex", config))["mcp_servers"]["unc_sol"]
    assert codex["required"] is False and codex["env_vars"] == ["UNC_SOL_TEST_KEY"]
    assert codex["args"] == ["-m", "unc_sol_bridge", "serve", "--config", str(config.path)]
    assert json.loads(render("claude-code", config))["mcpServers"]["unc_sol"]["env"] == {"UNC_SOL_TEST_KEY": "${UNC_SOL_TEST_KEY}"}
    assert json.loads(render("vscode", config))["servers"]["unc_sol"]["env"] == {"UNC_SOL_TEST_KEY": "${input:unc-sol-key}"}
    target = tmp_path / "client" / "config.toml"
    target.parent.mkdir()
    target.write_text('model = "native"\n\n[mcp_servers.other]\ncommand = "other"\nrequired = false\n', encoding="utf-8")
    assert install("codex", target, render("codex", config)) == "installed"
    merged = tomllib.loads(target.read_text(encoding="utf-8"))
    assert merged["model"] == "native" and merged["mcp_servers"] == {"other": {"command": "other", "required": False}, "unc_sol": codex}
    assert len(list(target.parent.glob("config.toml.bak-*"))) == 1
    assert install("codex", target, render("codex", config)) == "unchanged"
    clash = target.with_name("clash.toml")
    clash.write_text('[mcp_servers.unc_sol]\ncommand = "something-else"\n', encoding="utf-8")
    with pytest.raises(BridgeError) as caught:
        install("codex", clash, render("codex", config))
    assert caught.value.kind == "install_conflict" and "something-else" in clash.read_text(encoding="utf-8")
