import json
import uuid
from pathlib import Path
import pytest
import cohort_lab.hosted as hosted
from cohort_lab.student import StudentWorkflow
from cohort_lab.workflow import WorkflowError


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(hosted, "release_manifest", lambda: {"release_hash": "test-release"})
    def factory(data, output, **kwargs):
        return StudentWorkflow(data, output, runner=lambda *a: {"ready": True},
                               evidence=lambda n: {"files": []}, **kwargs)
    return hosted.HostedLesson(tmp_path, lesson_factory=factory)


def job(run, action, step, **kwargs):
    return {"id": str(uuid.uuid4()), "run_id": run, "release_hash": "test-release", "checkpoint": step,
            "payload": {"action": action, **kwargs}}


def test_duplicate_request_does_not_advance_and_students_are_isolated(adapter):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert adapter.execute(job(a, "start", -1))["packet"]["step"] == 0
    advance = job(a, "message", 0, message="next step")
    result = adapter.execute(advance)
    assert result["packet"]["step"] == 1
    assert adapter.execute(advance) == result
    assert adapter.execute(job(b, "start", -1))["packet"]["step"] == 0
    question = adapter.execute(job(a, "message", 1, message="Why is this interesting?"))
    assert question["packet"]["step"] == 1 and not question["packet"]["advanced"]


def test_stale_step_and_changed_idempotent_payload_are_rejected(adapter):
    run = str(uuid.uuid4())
    first = job(run, "start", -1)
    adapter.execute(first)
    with pytest.raises(WorkflowError, match="checkpoint"):
        adapter.execute(job(run, "message", -1, message="next step"))
    first["payload"] = {"action": "message", "message": "next step"}
    with pytest.raises(WorkflowError, match="idempotency"):
        adapter.execute(first)


def test_questions_choices_and_uncertain_execution(adapter):
    run = str(uuid.uuid4())
    adapter.execute(job(run, "start", -1))
    adapter.execute(job(run, "message", 0, message="next step"))
    result = adapter.execute(job(run, "choose", 1, key="final_verdict", value="Test learner judgment", message="Test learner judgment"))
    assert result["packet"]["step"] == 1
    assert result["packet"]["choices"]["final_verdict"] == "Test learner judgment"
    bad = job(run, "choose", 1, key="recommended_action", value="Fabricated action", message="What would you recommend?")
    with pytest.raises(WorkflowError, match="verbatim"):
        adapter.execute(bad)
    with pytest.raises(WorkflowError, match="uncertain"):
        adapter.execute(bad)


def test_foreign_paths_and_sql_before_checkpoint_are_rejected(adapter, tmp_path):
    run = str(uuid.uuid4())
    adapter.execute(job(run, "start", -1))
    with pytest.raises(WorkflowError, match="after the cohort"):
        adapter.execute(job(run, "query", 0, sql="SELECT 1"))
    foreign = tmp_path / "another-student.csv"
    foreign.write_text("a\n1\n")
    with pytest.raises(WorkflowError, match="outside"):
        adapter.evidence_packet({"step": 0, "result": {"files": [{"path": str(foreign)}]}}, tmp_path / "isolated")


def test_nemotron_failure_preserves_actual_checkpoint(adapter):
    def fail(*args):
        raise TimeoutError("test outage")
    adapter.interpreter = fail
    run = str(uuid.uuid4())
    packet = adapter.execute(job(run, "start", -1))["packet"]
    assert packet["step"] == 0
    assert packet["interpretation"]["status"] == "unavailable"


def test_journey_interpretation_has_the_authored_content_not_only_an_image(tmp_path):
    from cohort_lab.business_journey import build_business_journey, STAGES
    output = tmp_path / 'workspace'
    build_business_journey(output / 'diagrams')
    (output / 'diagrams/business-journey.png').write_bytes(b'fixture image')
    lesson = StudentWorkflow(hosted.ROOT / 'data', output)
    evidence = lesson._evidence(2)
    packet = hosted.HostedLesson(tmp_path).evidence_packet({'step': 2, 'result': evidence}, output)
    artifact = next(a for a in packet['artifacts'] if a['name'] == 'diagrams/business-journey.json')
    journey = json.loads(artifact['text'])
    assert journey['evidence'] == 'conceptual'
    assert [row['stage'] for row in journey['stages']] == [row[0] for row in STAGES]
    assert journey['stages'][3]['potential_friction'] == 'Setup takes too long'
    assert len(json.dumps(packet)) < 65000


def test_large_model_summary_keeps_convergence_and_holdout_evidence(tmp_path):
    import hashlib
    output = tmp_path / 'workspace'
    output.mkdir()
    diagnostic = {'max_r_hat': 1.002, 'min_ess': 820, 'divergences': 0,
                  'parameter_summary': [{'name': 'parameter_' + str(i), 'mean': i / 100} for i in range(1000)]}
    summary = {'model': 'fixture sBG + Gamma', 'diagnostic': diagnostic,
               'backtest': {'retention_mae': 0.04, 'diagnostic': {**diagnostic, 'min_ess': 930}},
               'valuation_backtest': {'diagnostic': {**diagnostic, 'min_ess': 710},
                                      'n_forecast_cohorts': 11, 'n_payback_already_observed': 7,
                                      'n_payback_after_origin': 4, 'n_both_recovered': 4}}
    path = output / 'model_summary.json'
    path.write_text(json.dumps(summary), encoding='utf-8')
    assert path.stat().st_size > 32000
    packet = hosted.HostedLesson(tmp_path).evidence_packet({'step': 14, 'result': {'files': [{'path': str(path)}]}}, output)
    artifact = packet['artifacts'][0]
    extracted = artifact['computed_evidence']['summary']
    assert extracted['diagnostic']['max_r_hat'] == 1.002
    assert extracted['diagnostic']['divergences'] == 0
    assert extracted['backtest']['retention_mae'] == 0.04
    assert extracted['diagnostic']['min_ess'] == 820
    assert extracted['backtest']['diagnostic']['min_ess'] == 930
    assert extracted['valuation_backtest']['diagnostic']['min_ess'] == 710
    assert extracted['valuation_backtest']['n_payback_already_observed'] == 7
    assert extracted['valuation_backtest']['n_both_recovered'] == 4
    assert set(artifact['computed_evidence']['scope_by_summary_key']) == {'diagnostic', 'backtest', 'valuation_backtest'}
    assert 'parameter_summary' not in json.dumps(extracted)
    assert artifact['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(json.dumps(packet)) < 65000
