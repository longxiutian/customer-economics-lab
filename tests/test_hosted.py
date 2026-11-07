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
