import hashlib
import json

import pytest

from cohort_lab.student import LESSONS, StudentWorkflow
from cohort_lab.workflow import DATA_FILES, DATASET_VERSION, WorkflowError


@pytest.fixture
def setup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    manifest = {"dataset_version": DATASET_VERSION, "schema_version": "3.0", "data_as_of": "2026-01-01T00:00:00Z", "files": {}}
    for name in DATA_FILES:
        content = b"person_id,value\np1,1\n"
        (data / name).write_bytes(content)
        manifest["files"][name] = {"sha256": hashlib.sha256(content).hexdigest(), "row_count": 1}
    (data / "data_manifest.json").write_text(json.dumps(manifest))
    calls = []

    def runner(stage, data_dir, output_dir, choices):
        calls.append(stage)
        if stage == 7:
            report = output_dir / "report"
            report.mkdir(exist_ok=True)
            (report / "customer-economics-report.pdf").write_bytes(b"report")
        return {"ready": True, "stage": stage}

    def evidence(step):
        return {"shown": step}

    return data, tmp_path / "out", calls, runner, evidence


def lesson(setup):
    data, output, _, runner, evidence = setup
    return StudentWorkflow(data, output, runner=runner, evidence=evidence)


def advance(lab, target):
    while lab.status()["step"] < target:
        reply = lab.handle_message("next step")
        assert reply["advanced"], reply


def test_opening_does_not_run_analysis_and_one_consent_advances_one_checkpoint(setup):
    lab = lesson(setup)
    assert lab.start()["step"] == 0
    assert setup[2] == []
    assert not (setup[1] / "lab_state.json").exists()
    for expected in range(1, 7):
        reply = lab.handle_message(" NEXT STEP ")
        assert reply["step"] == expected
        assert reply["result"]["shown"] == expected
    assert setup[2] == [0, 1, 2, 3]  # Presentation-only checkpoints do not rerun computations.


@pytest.mark.parametrize("message", ["next", "go ahead", "Why is CAC higher?", "next step please", "next step\nnext step", "My answer is search", ""])
def test_nonconsent_never_advances(setup, message):
    lab = lesson(setup)
    lab.start()
    reply = lab.handle_message(message)
    assert not reply["advanced"]
    assert reply["step"] == 0
    assert setup[2] == []


def test_resume_and_choice_do_not_advance(setup):
    lab = lesson(setup)
    lab.start()
    advance(lab, 5)
    calls = list(setup[2])
    lab.set_choice("segmentation_rationale", "Compare need groups at a common horizon")
    resumed = lesson(setup)
    assert resumed.start()["step"] == 5
    assert resumed.status()["choices"]["segmentation_rationale"].startswith("Compare need")
    assert setup[2] == calls


def test_report_is_last_and_requires_real_judgments(setup):
    lab = lesson(setup)
    lab.start()
    for step in range(1, len(LESSONS) - 1):
        assert lab.handle_message("next step")["step"] == step
        assert 7 not in setup[2]
        assert not (setup[1] / "report/customer-economics-report.pdf").exists()
    blocked = lab.handle_message("next step")
    assert not blocked["advanced"]
    assert set(blocked["error"]["missing_choices"]) == {"final_verdict", "recommended_action"}
    lab.set_choice("final_verdict", "Customer economics are improving")
    lab.set_choice("recommended_action", "Expand search/build-skill while retaining holdouts")
    assert lab.status()["step"] == 17
    assert lab.handle_message("next step")["step"] == 18
    assert setup[2] == list(range(8))
    assert (setup[1] / "report/customer-economics-report.pdf").exists()
    assert not lab.handle_message("next step")["advanced"]


def test_changed_grouping_rewinds_lesson_and_archives_report(setup):
    lab = lesson(setup)
    lab.start()
    advance(lab, 17)
    lab.set_choice("final_verdict", "Mixed")
    lab.set_choice("recommended_action", "Wait for another wave")
    lab.handle_message("next step")
    reply = lab.set_choice("segmentation_rationale", "Check within-cell variance first")
    assert reply["step"] == 5
    assert (setup[1] / "lesson_state.json").exists()
    assert not (setup[1] / "report").exists()
    assert (setup[1] / "invalidated/revision-001/report/customer-economics-report.pdf").exists()
    assert lab.handle_message("next step")["step"] == 6


def test_setup_failure_needs_new_consent_and_retries_same_checkpoint(setup):
    ready = False
    calls = []

    def runner(stage, *_):
        calls.append(stage)
        return {"ready": ready}

    lab = StudentWorkflow(setup[0], setup[1], runner=runner, evidence=setup[4])
    lab.start()
    assert lab.handle_message("next step")["step"] == 0
    assert calls == [0]
    ready = True
    assert lab.status()["step"] == 0
    assert calls == [0]
    assert lab.handle_message("next step")["step"] == 1
    assert calls == [0, 0]


def test_missing_artifact_retry_does_not_rerun_successful_computation(setup):
    missing = True

    def evidence(step):
        if step == 2 and missing:
            raise WorkflowError("Missing rendered map")
        return {"shown": step}

    lab = StudentWorkflow(setup[0], setup[1], runner=setup[3], evidence=evidence)
    lab.start()
    lab.handle_message("next step")
    with pytest.raises(WorkflowError, match="rendered map"):
        lab.handle_message("next step")
    assert lab.status()["step"] == 1
    assert setup[2] == [0, 1]
    missing = False
    assert lab.handle_message("next step")["step"] == 2
    assert setup[2] == [0, 1]


def test_source_changes_fail_closed(setup, monkeypatch):
    lab = lesson(setup)
    lab.start()
    monkeypatch.setattr("cohort_lab.student.implementation_snapshot", lambda: {"changed": "hash"})
    with pytest.raises(WorkflowError, match="frozen implementation"):
        lab.handle_message("next step")
    assert setup[2] == []
