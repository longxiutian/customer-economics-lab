#!/usr/bin/env python3
"""Compare two fresh full-inference runs or two report replays with frozen fits.

Instructor/release use only. Byte equality is scoped to the same environment;
neither mode proves cross-platform identity or constitutes visual review.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_artifacts import read, sha, validate
from cohort_lab.workflow import implementation_snapshot

REQUIRED_ROOT_FILES = (
    "implementation_manifest.json", "analysis_input_manifest.json", "analysis_manifest.json",
    "analysis_summary.json", "model_manifest.json", "model_summary.json", "posterior_draws.json",
    "benchmark_manifest.json", "benchmark_summary.json", "diagnostics_manifest.json",
    "decision_metrics_manifest.json", "postestimation_manifest.json",
)


def compared_files(run: Path, pdf: bool) -> list[str]:
    """Canonical evidence only; exclude logs, previews, queries and learner state."""
    names = set(REQUIRED_ROOT_FILES)
    for folder, suffixes in {
        "tables": {".csv"}, "sql": {".sql"},
        "diagrams": {".json", ".sql", ".md", ".html", ".svg", ".png"},
        "report": {".tex", ".sty", ".csv", ".json"},
        "report/figures": {".png", ".pdf"}, "challenge": {".csv", ".json"},
    }.items():
        names.update(p.relative_to(run).as_posix() for p in (run / folder).glob("*") if p.suffix in suffixes)
    if (run / "report_replay.json").exists():
        names.add("report_replay.json")
    if pdf:
        names.add("report/customer-economics-report.pdf")
    missing = [name for name in names if not (run / name).is_file()]
    if missing:
        raise ValueError(f"Missing canonical artifacts: {sorted(missing)}")
    return sorted(names)


def command_for(run: Path, *, mode: str, source: Path, steps: int, pdf: bool) -> list[str]:
    if mode == "report":
        command = [sys.executable, str(ROOT / "scripts/replay_report.py"), "--source", str(source), "--output", str(run)]
        if not pdf:
            command.append("--no-pdf")
        return command + ["--instructor"]
    command = [sys.executable, str(ROOT / "lab.py"), "--output", str(run), "--steps", str(steps)]
    if not pdf:
        command.append("--no-pdf")
    return command + ["batch", "--instructor"]


def compare_runs(runs: list[Path], *, pdf: bool) -> dict:
    validations = [validate(run, pdf=pdf) for run in runs]
    files, other = [compared_files(run, pdf) for run in runs]
    if files != other:
        raise ValueError("Artifact inventory differs between runs")
    comparisons = {name: {"run_a_sha256": sha(runs[0] / name), "run_b_sha256": sha(runs[1] / name)} for name in files}
    mismatches = [name for name, values in comparisons.items() if values["run_a_sha256"] != values["run_b_sha256"]]
    return {"status": "pass" if not mismatches else "fail", "compared_files": len(files),
            "comparisons": comparisons, "mismatches": mismatches, "validations": validations}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("full", "report"), default="full")
    parser.add_argument("--source", type=Path, help="Verified fitted output for report mode; default examples/reference")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/reproducibility")
    parser.add_argument("--steps", type=int, help="Full-inference mode only; default 3000")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--parallel", action="store_true", help="Run the two isolated processes concurrently")
    args = parser.parse_args()
    if args.mode == "full" and args.source is not None:
        parser.error("--source is only used in report mode")
    if args.mode == "report" and args.steps is not None:
        parser.error("Report mode reuses fitted outputs; --steps would imply a refit")
    steps = 3000 if args.steps is None else args.steps
    if steps < 3000:
        parser.error("--steps must be at least 3000")
    source = (args.source or ROOT / "examples/reference").resolve()
    parent = args.output.resolve()
    if parent.exists() and any(parent.iterdir()):
        parser.error("Use a new empty reproducibility directory; prior receipts are preserved")
    snapshot = implementation_snapshot()
    parent.mkdir(parents=True, exist_ok=True)
    runs = [parent / "run-a", parent / "run-b"]
    def command(run):
        return command_for(run, mode=args.mode, source=source, steps=steps, pdf=not args.no_pdf)
    if args.parallel:
        with contextlib.ExitStack() as stack:
            jobs = []
            for run in runs:
                log = stack.enter_context((parent / (run.name + ".log")).open("w", encoding="utf-8"))
                jobs.append((run, subprocess.Popen(command(run), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)))
            failures = []
            for run, process in jobs:
                if process.wait():
                    failures.append(run.name)
                else:
                    print(f"{run.name} completed", flush=True)
            if failures:
                raise SystemExit(f"{failures} failed; inspect logs. No reproducibility claim made.")
    else:
        for run in runs:
            with (parent / (run.name + ".log")).open("w", encoding="utf-8") as log:
                completed = subprocess.run(command(run), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if completed.returncode:
                raise SystemExit(f"{run.name} failed; inspect its log. No reproducibility claim made.")
            print(f"{run.name} completed", flush=True)
    if snapshot != implementation_snapshot():
        raise ValueError("Implementation changed during verification; no reproducibility claim made")
    receipt = {"schema_version": 2, "mode": args.mode, "model_refit": args.mode == "full",
               "scope": "Two fresh processes on the same host, frozen data, source and locked environment. " +
                        ("Observed analysis, decision metrics, diagnostics, post-estimation, diagrams and report rebuilt; fitted baseline and neural outputs preserved." if args.mode == "report" else "Both models refitted; observed analysis, forecasts, challenge predictions, diagrams and report rebuilt."),
               "python": platform.python_version(), "platform": platform.platform(),
               "parallel_processes": args.parallel, "seed": 20261116 if args.mode == "full" else None,
               "steps": steps if args.mode == "full" else None, "uv_lock_sha256": sha(ROOT / "uv.lock"),
               "implementation_manifest_sha256": sha(runs[0] / "implementation_manifest.json"),
               "frozen_data_manifest_sha256": sha(ROOT / "data/data_manifest.json"),
               **compare_runs(runs, pdf=not args.no_pdf)}
    if args.mode == "report":
        receipt["preserved_fitted_artifacts"] = read(runs[0] / "report_replay.json")["preserved_fitted_artifacts"]
    (parent / "reproducibility.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "mode", "model_refit", "compared_files", "mismatches")}, indent=2))
    if receipt["mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
