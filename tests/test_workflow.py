import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from cohort_lab.workflow import DATA_FILES, InputIntegrityError, LabWorkflow, WorkflowError, run_batch, verify_frozen_inputs
from scripts.bootstrap import archive_url, install_archive


@pytest.fixture
def data_dir(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    manifest = {"dataset_version": "1.0", "schema_version": "1.0", "data_as_of": "2026-01-01T00:00:00Z", "files": {}}
    for name in DATA_FILES:
        content = "person_id,value\np1,1\n"
        (directory / name).write_bytes(content.encode("utf-8"))
        manifest["files"][name] = {"sha256": hashlib.sha256(content.encode()).hexdigest(), "row_count": 1}
    (directory / "data_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


@pytest.fixture
def sentinel_runner():
    calls = []

    def run(stage, data_dir, output_dir, choices):
        calls.append(stage)
        if stage == 3:
            (output_dir / "tables").mkdir(exist_ok=True)
            (output_dir / "tables" / "cohort_age_summary.csv").write_text("n\n2\n")
        if stage == 6:
            (output_dir / "model_summary.json").write_text('{"fit":true}')
            (output_dir / "tables" / "cohort_valuation.csv").write_text("ltv\n25\n")
        if stage == 7:
            (output_dir / "report").mkdir(exist_ok=True)
            (output_dir / "report" / "report.pdf").write_bytes(b"test artifact")
        return {"ready": True, "stage": stage, "choices_seen": choices}

    return calls, run


def test_explicit_next_advances_exactly_one_stage(data_dir, tmp_path, sentinel_runner):
    calls, run = sentinel_runner
    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    assert lab.start()["stage"] == 0
    assert calls == [0]
    first = lab.handle_message("next")
    assert first["state"]["completed_stage"] == 1
    assert calls == [0, 1]
    second = lab.handle_message(" NEXT ")
    assert second["state"]["completed_stage"] == 2
    assert calls == [0, 1, 2]


@pytest.mark.parametrize("message", ["Why is CAC lower?", "Change my conclusion", "next please", "go ahead", ""])
def test_questions_and_corrections_do_not_advance(data_dir, tmp_path, sentinel_runner, message):
    calls, run = sentinel_runner
    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    lab.start()
    reply = lab.handle_message(message)
    assert reply["advanced"] is False
    assert reply["state"]["completed_stage"] == 0
    assert calls == [0]


def test_resume_new_instance_preserves_current_stage_and_choice(data_dir, tmp_path, sentinel_runner):
    calls, run = sentinel_runner
    output = tmp_path / "out"
    first = LabWorkflow(data_dir, output, runner=run)
    first.start()
    first.handle_message("next")
    first.set_choice("segmentation_rationale", "Compare intended use, then verify on older cohorts.")
    resumed = LabWorkflow(data_dir, output, runner=run)
    assert resumed.start()["state"]["completed_stage"] == 1
    assert calls == [0, 1]
    response = resumed.handle_message("next")
    assert response["stage"] == 2
    assert response["result"]["choices_seen"]["segmentation_rationale"].startswith("Compare intended use")


def test_input_tampering_invalidates_and_fails_closed(data_dir, tmp_path, sentinel_runner):
    calls, run = sentinel_runner
    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    lab.start()
    lab.handle_message("next")
    (data_dir / "transactions.csv").write_text("person_id,value\np1,999\n")
    with pytest.raises(InputIntegrityError, match="Modified frozen input"):
        lab.handle_message("next")
    state = json.loads(lab.state_path.read_text())
    assert state["status"] == "invalidated"
    assert state["completed_stage"] == -1
    assert state["stages"] == {}
    assert calls == [0, 1]


def test_manifest_definition_change_is_also_detected(data_dir, tmp_path, sentinel_runner):
    _, run = sentinel_runner
    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    lab.start()
    manifest_path = data_dir / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["data_as_of"] = "2025-01-01T00:00:00Z"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(InputIntegrityError, match="changed since"):
        lab.status()


def test_core_implementation_change_invalidates_saved_stages(data_dir, tmp_path, sentinel_runner, monkeypatch):
    _, run = sentinel_runner
    monkeypatch.setattr("cohort_lab.workflow.implementation_snapshot", lambda: {"uv.lock": "release-hash"})
    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    lab.start()
    monkeypatch.setattr("cohort_lab.workflow.implementation_snapshot", lambda: {"uv.lock": "changed-hash"})
    with pytest.raises(InputIntegrityError, match="implementation or frozen environment changed"):
        lab.handle_message("next")
    state = json.loads(lab.state_path.read_text())
    assert state["completed_stage"] == -1
    assert state["status"] == "invalidated"


def test_changed_choice_invalidates_and_archives_downstream_evidence(data_dir, tmp_path, sentinel_runner):
    calls, run = sentinel_runner
    output = tmp_path / "out"
    lab = LabWorkflow(data_dir, output, runner=run)
    lab.start()
    lab.set_choice("final_verdict", "Mixed")
    lab.set_choice("recommended_action", "Review the next renewal cycle")
    for _ in range(7):
        lab.handle_message("next")
    assert (output / "report" / "report.pdf").exists()
    revised = lab.set_choice("segmentation_rationale", "Revisit composition rather than assume within-group improvement.")
    assert revised["state"]["completed_stage"] == 2
    assert not (output / "tables").exists()
    assert not (output / "model_summary.json").exists()
    assert not (output / "report").exists()
    assert (output / "invalidated" / "revision-001" / "report" / "report.pdf").exists()
    assert calls == list(range(8))
    assert lab.handle_message("next")["stage"] == 3


def test_final_verdict_change_only_rebuilds_report(data_dir, tmp_path, sentinel_runner):
    _, run = sentinel_runner
    output = tmp_path / "out"
    lab = LabWorkflow(data_dir, output, runner=run)
    lab.start()
    lab.set_choice("final_verdict", "Mixed")
    lab.set_choice("recommended_action", "Review the next renewal cycle")
    for _ in range(7):
        lab.handle_message("next")
    changed = lab.set_choice("final_verdict", "Mixed: observed acquisition improves, youngest LTV remains uncertain.")
    assert changed["state"]["completed_stage"] == 6
    assert (output / "model_summary.json").exists()
    assert not (output / "report").exists()


def test_model_configuration_change_invalidates_model_and_report(data_dir, tmp_path, sentinel_runner):
    _, run = sentinel_runner
    output = tmp_path / "out"
    lab = LabWorkflow(data_dir, output, runner=run, steps=100)
    lab.start()
    lab.set_choice("final_verdict", "Mixed")
    lab.set_choice("recommended_action", "Review the next renewal cycle")
    for _ in range(7):
        lab.handle_message("next")
    resumed = LabWorkflow(data_dir, output, runner=run, steps=200)
    status = resumed.status()
    assert status["state"]["completed_stage"] == 5
    assert not (output / "model_summary.json").exists()
    assert not (output / "report").exists()


def test_setup_failure_remains_at_setup_until_fixed(data_dir, tmp_path):
    ready = False
    calls = []

    def run(stage, *_):
        calls.append(stage)
        return {"ready": ready}

    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    assert lab.start()["advanced"] is False
    assert lab.status()["state"]["completed_stage"] == -1
    ready = True
    assert lab.handle_message("next")["stage"] == 0
    assert calls == [0, 0]


def test_guided_report_requires_the_learners_actual_judgment(data_dir, tmp_path, sentinel_runner):
    calls, run = sentinel_runner
    lab = LabWorkflow(data_dir, tmp_path / "out", runner=run)
    lab.start()
    for _ in range(6):
        lab.handle_message("next")
    result = lab.handle_message("next")
    assert result["advanced"] is False
    assert result["state"]["completed_stage"] == 6
    assert set(result["missing_choices"]) == {"final_verdict", "recommended_action"}
    assert calls == list(range(7))
    lab.set_choice("final_verdict", "Too early to tell for the youngest cohorts")
    lab.set_choice("recommended_action", "Reassess after another observed renewal month")
    assert lab.handle_message("next")["stage"] == 7


def test_undeclared_extra_csv_is_rejected(data_dir):
    (data_dir / "unexpected.csv").write_text("n\n1\n")
    with pytest.raises(InputIntegrityError, match="exactly the eight"):
        verify_frozen_inputs(data_dir)


def test_instructor_batch_does_not_overwrite_student_output(data_dir, tmp_path):
    output = tmp_path / "student-work"
    output.mkdir()
    choices = output / "learner_choices.json"
    choices.write_text('{"final_verdict":"my interpretation"}')
    with pytest.raises(WorkflowError, match="fresh empty"):
        run_batch(data_dir, output)
    assert json.loads(choices.read_text())["final_verdict"] == "my interpretation"


def _archive(tmp_path, extras=None):
    path = tmp_path / "lab.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in {"SKILL.md": "skill", "lab.py": "pass", "pyproject.toml": "[project]", **(extras or {})}.items():
            archive.writestr("lab-v1/" + name, content)
    return path


def test_archive_download_install_requires_no_git(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bootstrap must not invoke Git or any other subprocess.")
    monkeypatch.setattr(subprocess, "run", forbidden)
    destination = install_archive(_archive(tmp_path), tmp_path / "extracted")
    assert (destination / "SKILL.md").is_file()
    assert not (destination / ".git").exists()
    assert archive_url() == "https://github.com/longxiutian/customer-economics-lab/archive/v1.0.0.zip"


def test_archive_rejects_traversal_before_extracting(tmp_path):
    archive = _archive(tmp_path, {"../../escaped.txt": "bad"})
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError, match="Unsafe"):
        install_archive(archive, destination)
    assert not destination.exists()


def test_archive_never_overwrites_existing_directory(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="empty destination"):
        install_archive(_archive(tmp_path), destination)
    assert (destination / "keep.txt").read_text() == "keep"


def test_guided_state_works_from_source_zip_without_git(data_dir, tmp_path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name in ("SKILL.md", "lab.py", "pyproject.toml", "cohort_lab/__init__.py", "cohort_lab/workflow.py"):
            archive.write(root / name, "lab-v1/" + name)
        for item in data_dir.iterdir():
            archive.write(item, "lab-v1/data/" + item.name)
    extracted = install_archive(archive_path, tmp_path / "zip-lab")
    code = (
        "from pathlib import Path; from cohort_lab.workflow import LabWorkflow; "
        "w=LabWorkflow(Path('data'),Path('output'),runner=lambda stage,*args:{'ready':True}); "
        "w.start(); r=w.handle_message('Why?'); assert not r['advanced']; "
        "assert w.handle_message('next')['stage']==1; print('zip-guided-ok')"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=extracted, text=True, capture_output=True, check=True)
    assert result.stdout.strip() == "zip-guided-ok"
    assert not (extracted / ".git").exists()
