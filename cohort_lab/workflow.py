"""Durable, one-stage-at-a-time orchestration for the guided lab.

The CLI records explicit learner input; the accompanying skill is responsible
for passing the learner's actual message rather than manufacturing consent.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

DATASET_VERSION = "4.0"
DATA_FILES = (
    "people.csv", "subscription_periods.csv", "transactions.csv",
    "product_events.csv", "feedback.csv", "campaign_spend.csv",
    "acquisition_attribution.csv", "experiment_assignments.csv",
)
STAGES = (
    "Check the environment and understand the company question",
    "Inspect the sources and draw the system map",
    "Classify UCV fields and propose baseline segments",
    "Build the analytical views with DuckDB SQL",
    "Compare cohorts and diagnose the company's observed direction",
    "Check acquisition incrementality with experimental evidence",
    "Forecast immature cohorts and examine LTV and payback",
    "Write the company diagnosis and compile the report",
)
# Earliest stage whose interpretation depends on the learner's choice.
CHOICE_STAGES = {
    "segmentation_rationale": 2,
    "journey_hypothesis": 2,
    "provisional_verdict": 4,
    "final_verdict": 7,
    "recommended_action": 7,
}


class WorkflowError(RuntimeError):
    """A stage cannot safely proceed."""


class InputIntegrityError(WorkflowError):
    """Frozen inputs differ from their release manifest or saved state."""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_snapshot(root: Path | None = None) -> dict:
    """Fingerprint code, bundled dependencies and instructions, excluding outputs."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    paths = []
    for folder, pattern in (("cohort_lab", "*.py"), ("sql", "*.sql"), ("templates", "*"), ("skills/executive-report", "*"), ("assets/articles", "*"), ("docs", "*.md"), ("vendor/archify", "*")):
        directory = root / folder
        if directory.exists():
            paths.extend(p for p in directory.rglob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    paths.extend(root / name for name in ("lab.py", "SKILL.md", "pyproject.toml", "uv.lock", "vendor/archify-provenance.json") if (root / name).is_file())
    paths.extend(p for p in (root/'tools').glob('*') if p.is_file())
    paths.extend(p for p in (root/'scripts').glob('*') if p.suffix in {'.mjs', '.py'} and p.is_file())
    return {p.relative_to(root).as_posix(): _hash(p) for p in sorted(set(paths))}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_frozen_inputs(data_dir: Path) -> dict:
    """Check every released CSV before any guided or batch calculation."""
    data_dir = Path(data_dir)
    manifest_path = data_dir / "data_manifest.json"
    if not manifest_path.is_file():
        raise InputIntegrityError("Missing data_manifest.json; use the complete released data folder.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_version") != DATASET_VERSION:
        raise InputIntegrityError(f"Expected dataset version {DATASET_VERSION!r}.")
    declared = manifest.get("files", {})
    if set(declared) != set(DATA_FILES):
        raise InputIntegrityError("The manifest must declare exactly the eight released CSV sources.")
    found = {p.name for p in data_dir.glob("*.csv")}
    if found != set(DATA_FILES):
        raise InputIntegrityError("The data folder does not contain exactly the eight released CSVs.")
    hashes = {}
    for name in DATA_FILES:
        actual = _hash(data_dir / name)
        if actual != declared[name].get("sha256"):
            raise InputIntegrityError(f"Modified frozen input: {name}. Restore the released file before continuing.")
        hashes[name] = actual
    hashes["data_manifest.json"] = _hash(manifest_path)
    return {"dataset_version": DATASET_VERSION, "hashes": hashes}


def _preview_csv(path: Path, limit: int = 6) -> dict:
    if not path.exists():
        raise WorkflowError(f"Expected analytical output is missing: {path.name}")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) == limit:
                break
        return {"file": path.name, "columns": reader.fieldnames, "preview": rows}


def _readiness(data_dir: Path, need_pdf: bool = True) -> dict:
    packages = ("duckdb", "numpy", "pandas", "jax", "numpyro", "matplotlib", "jinja2")
    missing = [name for name in packages if importlib.util.find_spec(name) is None]
    cpu_ready = False
    cpu_detail = None
    if not missing:
        # Run a real device check with accelerators hidden. Merely finding the
        # Python packages does not establish that the CPU runtime loads.
        environment = os.environ.copy()
        environment.update(JAX_PLATFORMS="cpu", JAX_ENABLE_X64="true", CUDA_VISIBLE_DEVICES="-1")
        probe = subprocess.run([sys.executable, "-c",
            "import jax,json; print(json.dumps({'backend':jax.default_backend(),'x64':bool(jax.config.x64_enabled)}))"],
            env=environment,text=True,capture_output=True,timeout=30)
        if probe.returncode == 0:
            cpu_detail = json.loads(probe.stdout)
            cpu_ready = cpu_detail.get("backend") == "cpu" and cpu_detail.get("x64") is True
    node = shutil.which("node")
    node_version = None
    if node:
        result = subprocess.run([node, "--version"], text=True, capture_output=True, check=False, timeout=10)
        if result.returncode == 0:
            node_version = result.stdout.strip()
    try:
        node_ready = node_version is not None and int(node_version.lstrip("v").split(".")[0]) >= 20
    except ValueError:
        node_ready = False
    diagram_ready = False
    if node_ready:
        probe = subprocess.run([node, str(Path(__file__).resolve().parents[1]/'scripts/export_diagram_assets.mjs'), '--check'],
                               text=True, capture_output=True, check=False, timeout=30)
        diagram_ready = probe.returncode == 0
    python_ready = sys.version_info[:2] == (3, 12)
    requested_tex = os.environ.get("COHORT_TEX_ENGINE")
    tex_engine = (shutil.which(requested_tex) or (requested_tex if Path(requested_tex).is_file() else None)) if requested_tex else (shutil.which("tectonic") or shutil.which("pdflatex"))
    if not tex_engine and not requested_tex and sys.platform == "win32" and shutil.which("wsl"):
        probe = subprocess.run([shutil.which("wsl"), "--exec", "sh", "-lc", "command -v pdflatex"],
                               text=True, capture_output=True, check=False, timeout=20)
        if probe.returncode == 0 and probe.stdout.strip():
            tex_engine = "WSL pdflatex"
    manifest = json.loads((data_dir / "data_manifest.json").read_text(encoding="utf-8"))
    return {
        "ready": python_ready and not missing and cpu_ready and node_ready and diagram_ready and (bool(tex_engine) or not need_pdf),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_ready": python_ready,
        "missing_python_packages": missing,
        "cpu_model_ready": cpu_ready,
        "cpu_runtime": cpu_detail,
        "gpu_required": False,
        "node": node_version,
        "node_ready": node_ready,
        "diagram_renderer_ready": diagram_ready,
        "latex_engine": tex_engine,
        "pdf_required": need_pdf,
        "dataset_version": manifest["dataset_version"],
        "data_as_of": manifest.get("data_as_of"),
        "question": "Are we moving in the right direction as a company?",
        "setup_instruction": "Use Python 3.12 and uv sync --frozen; Node 20+, npm ci --prefix tools, and the pinned Playwright Chromium install support Archify exports.",
        "report_note": "The report step also requires the documented LaTeX renderer; check docs/setup.md before class.",
    }


def execute_stage(stage: int, data_dir: Path, output_dir: Path, choices: dict,
                  *, seed: int = 20261116, steps: int = 3000,
                  compile_pdf: bool = True) -> dict:
    """Use the single canonical implementation; imports are deliberately lazy."""
    if stage == 0:
        return _readiness(data_dir, need_pdf=compile_pdf)
    if stage == 1:
        from .diagrams import build_diagrams
        return build_diagrams(data_dir, output_dir)
    if stage == 2:
        result = {
            "ucv_categories": ["Identifiers", "Engagement", "Relationship", "Perception"],
            "candidate_segment_fields": ["primary_need", "age_band", "region", "original acquisition channel"],
            "instructions": [
                "Read diagrams/ucv-tables.json: one four-column field-name table per dataset. Use a best-fit category and explain ambiguous fields; preserve genuine gaps.",
                "Propose which baseline grouping may explain retention and contribution differences.",
                "The introductory business map describes possible benefits and friction; distinguish observed events, reported perceptions and hypotheses.",
                "Stage 4 will check the proposal against older age-aligned cohorts; do not claim an outcome comparison yet.",
            ],
            "choices": choices,
            "diagrams": ["diagrams/source-systems.html", "diagrams/knowledge-assets.html", "diagrams/business-journey.html"],
            "ucv_tables": ["diagrams/ucv-tables.md", "diagrams/ucv-tables.json"],
        }
        _write_json(output_dir / "stage2_customer_reasoning.json", result)
        return result
    if stage == 3:
        from .analysis import build_views
        return build_views(data_dir, output_dir)
    if stage == 4:
        from .analysis import validate_analysis
        from .report import build_charts
        validate_analysis(output_dir)
        return {
            "charts": build_charts(output_dir),
            "segmentation": _preview_csv(output_dir / "tables" / "segmentation_comparison.csv"),
            "question": "Are successive acquisition cohorts improving at equivalent ages? What changes after breaking out segment and channel mix?",
        }
    if stage == 5:
        from .analysis import validate_analysis
        validate_analysis(output_dir)
        table_dir = output_dir / "tables"
        result = {"assignments_summary": _preview_csv(table_dir / "experiment_summary.csv")}
        if (table_dir / "experiment_effects.csv").exists():
            result["effects"] = _preview_csv(table_dir / "experiment_effects.csv")
        result["interpretation"] = (
            "Keep all assigned prospects and each experiment's own control. The test identifies its tested context; "
            "historical cohort differences and buyer LTV are not automatically causal marketing effects."
        )
        return result
    if stage == 6:
        from .model import fit_and_forecast
        from .benchmark import run_benchmark, validate_retention_comparison
        from .report import build_charts
        import pandas as pd
        model_result = fit_and_forecast(output_dir, seed=seed, steps=steps)
        benchmark = run_benchmark(pd.read_csv(output_dir/'tables/cohort_age_summary.csv'), output_dir, seed=seed)
        validate_retention_comparison(output_dir)
        from .challenge import baseline_predictions
        challenge = baseline_predictions(output_dir)
        return {"model": model_result, "benchmark": benchmark, "charts": build_charts(output_dir),
                "optional_model_challenge": challenge}
    if stage == 7:
        from .report import build_report
        if choices:
            _write_json(output_dir / "learner_choices.json", choices)
        return build_report(output_dir, compile_pdf=compile_pdf)
    raise WorkflowError(f"Unknown stage {stage}.")


class LabWorkflow:
    """Persist learner choices and completed stages without advancing on questions."""

    def __init__(self, data_dir: Path, output_dir: Path, *, runner: Callable | None = None,
                 seed: int = 20261116, steps: int = 3000, compile_pdf: bool = True):
        self.data_dir = Path(data_dir).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.state_path = self.output_dir / "lab_state.json"
        self.seed, self.steps, self.compile_pdf = seed, steps, compile_pdf
        self.runner = runner

    def _load(self) -> dict:
        if not self.state_path.exists():
            raise WorkflowError("No saved lab exists here. Start the guided lab first.")
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self, state: dict) -> None:
        _write_json(self.state_path, state)

    def _check_inputs(self, state: dict) -> None:
        try:
            current = verify_frozen_inputs(self.data_dir)
            if current != state["inputs"]:
                raise InputIntegrityError("The frozen dataset or its manifest changed since this lab began.")
            if implementation_snapshot() != state.get("implementation"):
                raise InputIntegrityError("The lab implementation or frozen environment changed since this lab began. Restore the release or start in a new output folder.")
        except (InputIntegrityError, OSError, ValueError, KeyError) as exc:
            self._invalidate(state, 0, "input_change")
            state["status"] = "invalidated"
            state["error"] = str(exc)
            self._save(state)
            raise InputIntegrityError(str(exc)) from exc
        if state.get("status") == "invalidated":
            raise InputIntegrityError("Restore released inputs and explicitly restart in a new output folder.")
        configuration = {"seed": self.seed, "steps": self.steps, "compile_pdf": self.compile_pdf}
        previous = state.get("configuration", configuration)
        if previous != configuration:
            changed_stage = 6 if (previous["seed"], previous["steps"]) != (self.seed, self.steps) else 7
            self._invalidate(state, changed_stage, "run_configuration_changed")
            state["configuration"] = configuration
            self._save(state)

    def _invalidate(self, state: dict, from_stage: int, reason: str) -> None:
        removed = {key: value for key, value in state["stages"].items() if int(key) >= from_stage}
        if removed:
            archived = self._archive_artifacts(from_stage, len(state["invalidations"]) + 1, removed)
            state["invalidations"].append({"from_stage": from_stage, "reason": reason, "stages": removed,
                                           "archived_artifacts": archived})
        state["stages"] = {key: value for key, value in state["stages"].items() if int(key) < from_stage}
        state["completed_stage"] = min(state["completed_stage"], from_stage - 1)
        state["status"] = "waiting"

    def _archive_artifacts(self, from_stage: int, revision: int, removed: dict) -> list[str]:
        """Keep old evidence recoverable while preventing stale previews."""
        names = ["report", "implementation_manifest.json", "report_replay.json"]
        if from_stage <= 4:
            names += ["decision_metrics_manifest.json", "tables/segmentation_objective.csv", "tables/cac_reconciliation.csv"]
            names += ["diagnostics_manifest.json", "tables/friction_contrasts.csv", "tables/friction_balance.csv", "tables/friction_refund_sensitivity.csv"]
        if from_stage <= 6:
            names += ["postestimation_manifest.json", "tables/segment_forecast_curves.csv", "tables/strategic_segment_breakout.csv", "tables/strategic_rank_stability.csv"]
            names += ["model_summary.json", "model_manifest.json", "model", "challenge", "tables/cohort_valuation.csv",
                      "tables/cohort_valuation_by_segment.csv", "tables/backtest.csv", "tables/valuation_backtest.csv", "tables/forecast_curve.csv",
                      "tables/forecast_curves.csv", "tables/model_predictions.csv", "model_artifacts",
                      "model_draws.npz", "posterior_draws.json"]
        if from_stage <= 3:
            # Everything produced after stage 2 belongs to the canonical build.
            preserved = {"lab_state.json", "learner_choices.json", "invalidated", "diagrams", "stage2_customer_reasoning.json"}
            names = [p.name for p in self.output_dir.iterdir() if p.name not in preserved]
        if from_stage <= 2:
            names += ["stage2_customer_reasoning.json"]
        if from_stage <= 1:
            names += ["diagrams"]
        def declared_artifacts(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "artifacts" and isinstance(item, list):
                        for artifact in item:
                            if isinstance(artifact, str):
                                names.append(artifact)
                    else:
                        declared_artifacts(item)
            elif isinstance(value, list):
                for item in value:
                    declared_artifacts(item)
        declared_artifacts(removed)
        archive = self.output_dir / "invalidated" / f"revision-{revision:03d}"
        archived = []
        for name in dict.fromkeys(names):
            if Path(name).is_absolute():
                try:
                    name = str(Path(name).resolve().relative_to(self.output_dir))
                except ValueError as exc:
                    raise WorkflowError("An artifact manifest points outside the lab output directory.") from exc
            source = self.output_dir / name
            if not source.exists():
                continue
            target = archive / name
            if not source.resolve().is_relative_to(self.output_dir) or not target.resolve().is_relative_to(self.output_dir):
                raise WorkflowError("Refusing to archive an output path outside the lab output directory.")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            archived.append(name)
        return archived

    def _run(self, state: dict, stage: int) -> dict:
        self._check_inputs(state)
        try:
            if self.runner:
                result = self.runner(stage, self.data_dir, self.output_dir, dict(state["choices"]))
            else:
                result = execute_stage(stage, self.data_dir, self.output_dir, dict(state["choices"]),
                                       seed=self.seed, steps=self.steps, compile_pdf=self.compile_pdf)
        except Exception as exc:
            state["status"] = "blocked"
            state["error"] = str(exc)
            self._save(state)
            raise WorkflowError(f"Stage {stage} did not complete: {exc}") from exc
        if stage == 0 and not result.get("ready", True):
            state["status"] = "blocked"
            state["setup_result"] = result
            self._save(state)
            return {"advanced": False, "stage": 0, "result": result, "state": state}
        state["stages"][str(stage)] = {"title": STAGES[stage], "result": result}
        state["completed_stage"] = stage
        state["status"] = "complete" if stage == len(STAGES) - 1 else "waiting"
        state.pop("error", None)
        self._save(state)
        return {"advanced": True, "stage": stage, "result": result, "state": state,
                "message": "Lab complete." if state["status"] == "complete" else "Type next to continue."}

    def start(self) -> dict:
        if self.state_path.exists():
            return self.status()
        inputs = verify_frozen_inputs(self.data_dir)
        state = {"schema_version": 1, "completed_stage": -1, "status": "waiting", "inputs": inputs,
                 "implementation": implementation_snapshot(),
                 "configuration": {"seed": self.seed, "steps": self.steps, "compile_pdf": self.compile_pdf},
                 "choices": {}, "stages": {}, "invalidations": [], "messages": []}
        self._save(state)
        return self._run(state, 0)

    def status(self) -> dict:
        state = self._load()
        self._check_inputs(state)
        return {"advanced": False, "state": state, "next_stage": min(state["completed_stage"] + 1, len(STAGES)),
                "message": "Resume the existing stage. Only an explicit next advances."}

    def handle_message(self, message: str) -> dict:
        state = self._load()
        self._check_inputs(state)
        explicit_next = message.strip().casefold() == "next"
        state["messages"].append({"stage": state["completed_stage"], "text": message, "explicit_next": explicit_next})
        self._save(state)
        if not explicit_next:
            return {"advanced": False, "state": state,
                    "message": "Answer or revise within the current stage; no stage was advanced."}
        upcoming = state["completed_stage"] + 1
        if upcoming >= len(STAGES):
            return {"advanced": False, "state": state, "message": "All stages are complete."}
        if upcoming == 7:
            missing = [key for key in ("final_verdict", "recommended_action") if not state["choices"].get(key, "").strip()]
            if missing:
                return {"advanced": False, "state": state, "missing_choices": missing,
                        "message": "Record the learner's final verdict and recommended action before compiling their report. Then type next."}
        return self._run(state, upcoming)

    def set_choice(self, key: str, value: str) -> dict:
        if key not in CHOICE_STAGES:
            raise WorkflowError("Supported choice keys: " + ", ".join(CHOICE_STAGES))
        state = self._load()
        self._check_inputs(state)
        if state["choices"].get(key) == value:
            return {"advanced": False, "state": state, "changed": False}
        state["choices"][key] = value
        # First recording during its own stage does not erase that stage. A
        # revision after dependent stages exist invalidates only those stages.
        from_stage = CHOICE_STAGES[key] + 1
        if state["completed_stage"] >= from_stage:
            self._invalidate(state, from_stage, f"choice_changed:{key}")
        # Any already-built report must be rebuilt after a final judgment edit.
        if key in ("final_verdict", "recommended_action") and state["completed_stage"] == 7:
            self._invalidate(state, 7, f"choice_changed:{key}")
        _write_json(self.output_dir / "learner_choices.json", state["choices"])
        self._save(state)
        return {"advanced": False, "state": state, "changed": True,
                "message": "Choice saved. Type next when ready to continue; downstream stage records may need rebuilding."}


def run_batch(data_dir: Path, output_dir: Path, *, seed: int = 20261116,
              steps: int = 3000, compile_pdf: bool = True) -> dict:
    """Explicit instructor reproducibility mode, never the guided-chat default."""
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise WorkflowError("Use a fresh empty output directory for an instructor batch run.")
    verify_frozen_inputs(Path(data_dir))
    results = {}
    for stage in (1, 3, 4, 5, 6, 7):
        results[str(stage)] = execute_stage(stage, Path(data_dir), Path(output_dir), {},
                                            seed=seed, steps=steps, compile_pdf=compile_pdf)
    return results
