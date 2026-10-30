#!/usr/bin/env python3
"""Instructor report replay from verified fitted outputs, without refitting."""
from pathlib import Path
import argparse
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cohort_lab.analysis import build_views, _hash
from cohort_lab.benchmark import validate_benchmark
from cohort_lab.diagrams import build_diagrams
from cohort_lab.report import build_report, _validate_model_outputs
from cohort_lab.workflow import verify_frozen_inputs


def replay(source: Path, output: Path, *, compile_pdf: bool = True) -> dict:
    source, output = source.resolve(), output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a fresh empty report replay directory")
    verify_frozen_inputs(ROOT / "data")
    _validate_model_outputs(source); validate_benchmark(source)
    output.mkdir(parents=True, exist_ok=True)
    build_views(ROOT / "data", output)
    preserved = {}
    for name in ["model_manifest.json", "benchmark_manifest.json"]:
        manifest = json.loads((source / name).read_text(encoding="utf-8"))
        for relative in [name] + list(manifest["output_hashes"]):
            target = output / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
            preserved[relative] = _hash(target)
    _validate_model_outputs(output); validate_benchmark(output)
    build_diagrams(ROOT / "data", output)
    report = build_report(output, compile_pdf=compile_pdf)
    receipt = {"scope": "Fresh observed ETL, diagnostics, decision metrics, post-estimation, diagrams and report; verified baseline and neural fitted outputs reused unchanged. No refit or future outcomes.",
               "compiled": compile_pdf, "model_refit": False,
               "source_model_manifest_sha256": _hash(source / "model_manifest.json"),
               "frozen_data_manifest_sha256": _hash(ROOT / "data/data_manifest.json"),
               "preserved_fitted_artifacts": preserved, "report_sha256": report.get("build", {}).get("pdf_sha256")}
    (output / "report_replay.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--instructor", action="store_true", required=True)
    parser.add_argument("--no-pdf", action="store_true", help="Rebuild editable TeX; do not claim a compiled PDF")
    args = parser.parse_args()
    print(json.dumps(replay(args.source, args.output, compile_pdf=not args.no_pdf), indent=2))
