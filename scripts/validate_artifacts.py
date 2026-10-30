#!/usr/bin/env python3
"""Validate the complete public report evidence chain without recomputing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(path: Path, expected: str) -> None:
    if not path.is_file() or sha(path) != expected:
        raise ValueError(f"Missing or changed artifact: {path}")


def check_files(base: Path, hashes: dict) -> None:
    if not hashes:
        raise ValueError(f"Missing artifact hash inventory for {base}")
    for name, expected in hashes.items():
        path = (base / name).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ValueError(f"Artifact path escapes its directory: {name}")
        check(path, expected)


def validate(output: Path, *, pdf: bool = True, companion: bool = False) -> dict:
    """Check current sources, derived artifacts and their saved relationships."""
    from cohort_lab.workflow import implementation_snapshot, verify_frozen_inputs
    from cohort_lab.data import validate_data
    from cohort_lab.analysis import validate_analysis
    from cohort_lab.benchmark import validate_benchmark, validate_retention_comparison
    from cohort_lab.diagnostics import validate_diagnostics
    from cohort_lab.postestimation import validate_postestimation
    from cohort_lab.decision_metrics import validate_decision_metrics
    from cohort_lab.report import _validate_model_outputs, _validate_style, _pdf_copyability

    output = output.resolve()
    verify_frozen_inputs(ROOT / "data")
    validate_data(ROOT / "data")
    if read(output / "implementation_manifest.json") != implementation_snapshot():
        raise ValueError("Implementation, instructions or locked environment changed; rebuild in a fresh folder")
    for validator in (validate_analysis, _validate_model_outputs, validate_benchmark,
                      validate_retention_comparison, validate_diagnostics,
                      validate_postestimation, validate_decision_metrics):
        validator(output)
    inputs = read(output / "analysis_input_manifest.json")
    check(ROOT / "data/data_manifest.json", inputs["data_manifest_sha256"])
    check_files(ROOT / "data", {k: v["sha256"] for k, v in inputs["files"].items()})
    analysis = read(output / "analysis_manifest.json")
    check(ROOT / "data/data_manifest.json", analysis["input_data_manifest_sha256"])
    check_files(ROOT / "data", analysis["input_csv_hashes"])

    diagrams = read(output / "diagrams/diagram_manifest.json")
    check_files(output, diagrams["output_hashes"])
    check_files(ROOT, diagrams["knowledge_asset_hashes"])
    check(ROOT / "scripts/export_diagram_assets.mjs", diagrams["static_renderer"]["script_sha256"])
    for source in diagrams["sources"]:
        check(ROOT / "data" / source["file"], source["sha256"])
    charts = read(output / "report/chart_manifest.json")
    check_files(output / "tables", charts["sources"])
    for figure in charts["figures"].values():
        if set(figure["files"]) != set(figure["sha256"]):
            raise ValueError("Incomplete figure hash inventory")
        check_files(output / "report/figures", figure["sha256"])
    for name in ("diagnostics_manifest", "decision_metrics_manifest", "postestimation_manifest", "model_summary"):
        check(output / (name + ".json"), charts[name + "_sha256"])

    report = read(output / "report/report_manifest.json")
    bindings = {
        "implementation_manifest": "implementation_manifest.json",
        "report_source": "report/customer-economics-report.tex",
        "style": "report/labreport.sty", "upstream_style": "report/longxiu-research-brief.sty",
        "parameter_summary": "tables/parameter_summary.csv",
        "executive_metrics": "report/executive_metrics.csv",
        "matched_cohort_comparison": "report/matched_cohort_comparison.json",
        "diagram_manifest": "diagrams/diagram_manifest.json", "ucv": "diagrams/ucv-tables.json",
        "chart_manifest": "report/chart_manifest.json", "exhibit_registry": "report/exhibit_registry.json",
        **{n: n + ".json" for n in ("analysis_summary", "model_summary", "benchmark_manifest",
                                   "diagnostics_manifest", "postestimation_manifest", "decision_metrics_manifest")},
    }
    for key, relative in bindings.items():
        check(output / relative, report[key + "_sha256"])
    for key, relative in {"style": "templates/labreport.sty", "upstream_style": "templates/longxiu-research-brief.sty",
                          "template": "templates/customer-economics-report.tex.j2", "display_formatter": "cohort_lab/display.py",
                          "report_skill": "skills/executive-report/SKILL.md"}.items():
        check(ROOT / relative, report[key + "_sha256"])
    check_files(output / "tables", report["tables"])
    if report["learner_choices_sha256"] is not None:
        check(output / "learner_choices.json", report["learner_choices_sha256"])
    elif (output / "learner_choices.json").exists():
        raise ValueError("Unbound learner choices; rebuild the report")
    _validate_style()
    if pdf:
        if not report["compiled"] or report["build"]["overfull_boxes"] != 0:
            raise ValueError("A successfully compiled PDF without overfull boxes is required")
        check(output / "report/customer-economics-report.pdf", report["build"]["pdf_sha256"])
        _pdf_copyability(output / "report/customer-economics-report.pdf")
    if companion:
        provenance = read(ROOT / "teaching/companion-provenance.json")
        for extension in ("pdf", "pptx"):
            check(ROOT / f"teaching/customer-economics-lab.{extension}", provenance[extension + "_sha256"])
        check_files(output / "tables", provenance["source_table_hashes"])
    return {"status": "pass", "pdf_verified": pdf, "companion_integrity_verified": companion,
            "implementation_files": len(read(output / "implementation_manifest.json")),
            "scope": "Current-source and saved-artifact integrity; not a new fit, independent numerical reanalysis or visual review."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "examples/reference")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--companion", action="store_true", help="Also check preserved teaching files and their source-table hashes.")
    args = parser.parse_args()
    print(json.dumps(validate(args.output, pdf=not args.no_pdf, companion=args.companion), indent=2))
