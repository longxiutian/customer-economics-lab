import json
import shutil
from pathlib import Path

import pytest

from cohort_lab.workflow import implementation_snapshot
from scripts import verify_reproducibility as verifier
from scripts.validate_artifacts import validate

ROOT = Path(__file__).resolve().parents[1]


def test_instruction_script_and_vendor_edits_change_the_snapshot(tmp_path):
    names = ["SKILL.md", "scripts/replay_report.py", "docs/cac-incrementality.md",
             "skills/executive-report/references/style-system.md", "vendor/archify/renderers/example.mjs"]
    for name in names + ["outputs/guided/queries/question.sql"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original", encoding="utf-8")
    original = implementation_snapshot(tmp_path)
    assert set(original) == set(names)
    for name in names:
        (tmp_path / name).write_text("changed", encoding="utf-8")
        assert implementation_snapshot(tmp_path)[name] != original[name]
        (tmp_path / name).write_text("original", encoding="utf-8")
    (tmp_path / "outputs/guided/queries/question.sql").write_text("new question", encoding="utf-8")
    assert implementation_snapshot(tmp_path) == original


def test_inventory_includes_new_manifests_and_sql_but_not_visual_qa(tmp_path):
    extra = ["sql/02_friction.sql", "tables/cac_reconciliation.csv", "diagrams/inspection.sql",
             "diagrams/ucv-tables.md", "diagrams/business-journey.json", "report/chart_manifest.json",
             "report/customer-economics-report.tex", "report/figures/cac.pdf"]
    excluded = ["report/preview.png", "report/build.log", "queries/question.sql", "lab_state.json"]
    for name in list(verifier.REQUIRED_ROOT_FILES) + extra + excluded:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    assert set(verifier.compared_files(tmp_path, False)) == set(verifier.REQUIRED_ROOT_FILES) | set(extra)
    (tmp_path / "decision_metrics_manifest.json").unlink()
    with pytest.raises(ValueError, match="Missing canonical artifacts"):
        verifier.compared_files(tmp_path, False)


def test_report_mode_uses_replay_without_model_step_arguments(tmp_path):
    command = verifier.command_for(tmp_path / "out", mode="report", source=tmp_path / "fit", steps=9000, pdf=False)
    assert Path(command[1]).name == "replay_report.py"
    assert command[command.index("--source") + 1] == str(tmp_path / "fit")
    assert "--no-pdf" in command and "--steps" not in command and "batch" not in command
    full = verifier.command_for(tmp_path / "out", mode="full", source=tmp_path / "fit", steps=4000, pdf=True)
    assert Path(full[1]).name == "lab.py" and full[-2:] == ["batch", "--instructor"]
    assert full[full.index("--steps") + 1] == "4000" and "--source" not in full


@pytest.fixture(scope="module")
def verified_reference(tmp_path_factory):
    output = tmp_path_factory.mktemp("reference") / "run"
    shutil.copytree(ROOT / "examples/reference", output)
    assert validate(output, companion=True)["status"] == "pass"
    return output


@pytest.mark.parametrize("relative", [
    "tables/cac_reconciliation.csv", "decision_metrics_manifest.json",
    "diagrams/business-journey.svg", "report/figures/channel-segment-retention.png",
    "report/labreport.sty", "implementation_manifest.json",
])
def test_identically_tampered_runs_cannot_pass(verified_reference, relative):
    path = verified_reference / relative
    original = path.read_bytes()
    try:
        if path.suffix == ".json":
            value = json.loads(original)
            key = "code_sha256" if relative == "decision_metrics_manifest.json" else next(iter(value))
            value[key] = "invalid"
            path.write_text(json.dumps(value), encoding="utf-8")
        else:
            path.write_bytes(original + b"\nchanged")
        # Same directory twice deliberately makes byte comparison vacuous.
        # Validation must reject it before declaring reproducibility.
        with pytest.raises(ValueError):
            verifier.compare_runs([verified_reference, verified_reference], pdf=True)
    finally:
        path.write_bytes(original)
