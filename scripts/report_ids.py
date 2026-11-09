#!/usr/bin/env python3
"""Read invisible report IDs and group duplicate runs; no server or personal data."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cohort_lab.report_identity import inspect_pdf


def summarize(paths):
    groups, invalid = {}, []
    for path in sorted(set(Path(p).resolve() for p in paths)):
        try:
            report_id = inspect_pdf(path)["report_id"]
            groups.setdefault(report_id, []).append(str(path))
        except Exception as exc:
            invalid.append({"file": str(path), "error": str(exc)})
    return {"distinct_report_runs": len(groups), "reports": groups,
            "duplicate_ids": {key: files for key, files in groups.items() if len(files) > 1},
            "unmarked_or_invalid": invalid,
            "scope": "Distinct report-run IDs, not authenticated students or proof of independent work."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="PDF files or folders of PDFs (not recursive)")
    args = parser.parse_args()
    files = [file for path in args.paths for file in (path.glob("*.pdf") if path.is_dir() else [path])]
    print(json.dumps(summarize(files), indent=2))
