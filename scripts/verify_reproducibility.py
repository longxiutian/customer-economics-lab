#!/usr/bin/env python3
"""Validate and compare two completed runs without advancing a lesson."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_artifacts import sha, validate

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
    if (run / "report_identity.json").exists():
        names.add("report_identity.json")
    if pdf:
        names.add("report/customer-economics-report.pdf")
    missing = [name for name in names if not (run / name).is_file()]
    if missing:
        raise ValueError(f"Missing canonical artifacts: {sorted(missing)}")
    return sorted(names)


def comparison_hash(run: Path, name: str, *, ignore_report_identity: bool = False) -> str:
    if not ignore_report_identity:
        return sha(run / name)
    import hashlib
    if name == "report/customer-economics-report.pdf":
        from cohort_lab.report_identity import content_sha256
        return content_sha256(run / name)
    if name in {"report_identity.json", "report/report_manifest.json"}:
        value = json.loads((run / name).read_text(encoding="utf-8"))
        if name == "report_identity.json":
            value["report_id"] = "<run-specific>"
        elif value.get("version", 0) >= 4:
            value["report_identity"]["report_id"] = "<run-specific>"
            value["report_identity_sha256"] = "<run-specific>"
            if value.get("compiled"):
                value["invisible_footer"]["report_id"] = "<run-specific>"
                value["build"]["pdf_sha256"] = value["invisible_footer"]["content_sha256"]
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return sha(run / name)


def compare_runs(runs: list[Path], *, pdf: bool, ignore_report_identity: bool = False) -> dict:
    validations = [validate(run, pdf=pdf) for run in runs]
    files, other = [compared_files(run, pdf) for run in runs]
    if files != other:
        raise ValueError("Artifact inventory differs between runs")
    comparisons = {name: {
        "run_a_sha256": comparison_hash(runs[0], name, ignore_report_identity=ignore_report_identity),
        "run_b_sha256": comparison_hash(runs[1], name, ignore_report_identity=ignore_report_identity)} for name in files}
    mismatches = [name for name, values in comparisons.items() if values["run_a_sha256"] != values["run_b_sha256"]]
    return {"status": "pass" if not mismatches else "fail", "compared_files": len(files),
            "comparisons": comparisons, "mismatches": mismatches, "validations": validations,
            "report_identity_ignored": ignore_report_identity}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", type=Path, required=True)
    parser.add_argument("--run-b", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True, help="New JSON receipt; existing files are preserved")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--ignore-report-identity", action="store_true",
                        help="Validate each run, then compare content excluding only its invisible run ID")
    args = parser.parse_args()
    runs = [args.run_a.resolve(), args.run_b.resolve()]
    if runs[0] == runs[1]:
        parser.error("Use two distinct completed runs")
    if args.receipt.exists():
        parser.error("Preserve the existing receipt and choose a new path")
    receipt = {"schema_version":3, "mode":"compare_completed_runs", "model_refit":False,
               "scope":"Integrity validation and byte comparison only. No analysis, fitting, report generation or lesson advancement was performed. Consult each run's receipts for its creation and environment.",
               "verifier_python":platform.python_version(), "verifier_platform":platform.platform(),
               "runs":[str(run) for run in runs], **compare_runs(runs,pdf=not args.no_pdf,ignore_report_identity=args.ignore_report_identity)}
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    with args.receipt.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:receipt[k] for k in ('status','mode','model_refit','compared_files','mismatches')},indent=2))
    if receipt["mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
