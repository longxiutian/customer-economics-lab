#!/usr/bin/env python3
"""Public command-line entrypoint. Guided mode never runs ahead."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cohort_lab.workflow import LabWorkflow, WorkflowError, run_batch, verify_frozen_inputs

ROOT = Path(__file__).resolve().parent


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="From separate customer CSVs to a company diagnosis.")
    p.add_argument("--data", type=Path, default=ROOT / "data")
    p.add_argument("--output", type=Path, default=ROOT / "outputs" / "guided")
    p.add_argument("--seed", type=int, default=20261116)
    p.add_argument("--steps", type=int, default=3000, help="NumPyro fit budget (at least 3000); changing it invalidates saved model/report stages.")
    p.add_argument("--no-pdf", action="store_true", help="Generate editable TeX without compiling the final PDF.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="Run only setup stage 0, or resume an existing guided lab.")
    sub.add_parser("status", help="Read saved progress without advancing.")
    message = sub.add_parser("message", help="Record the actual learner message. Only exactly 'next' advances one stage.")
    message.add_argument("text")
    choice = sub.add_parser("choose", help="Save a learner judgment without advancing.")
    choice.add_argument("key")
    choice.add_argument("value")
    query = sub.add_parser("query", help="Execute and log one read-only SQL question without advancing the guided stage.")
    query.add_argument("--sql-file", type=Path, help="SQL file; omit to read SQL from standard input.")
    query.add_argument("--max-rows", type=int, default=10000)
    query.add_argument("--timeout", type=float, default=20.0)
    query.add_argument("--instructor", action="store_true", help="Allow verified batch output without guided state.")
    sub.add_parser("validate-data", help="Validate frozen CSV hashes and the full data contract.")
    sub.add_parser("challenge-template", help="Create observed-only future keys and a blank submission without advancing.")
    sub.add_parser("challenge-baseline", help="Forecast the next twelve calendar months using an existing verified fit.")
    submission = sub.add_parser("validate-submission", help="Check future prediction format against observed-only keys; no hidden labels are read.")
    submission.add_argument("--csv", type=Path, required=True)
    batch = sub.add_parser("batch", help="Explicit instructor reproducibility run; not for guided learner sessions.")
    batch.add_argument("--instructor", action="store_true", required=True)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.steps < 3000:
        parser().error("--steps must be at least 3000 for the validated release model")
    try:
        workflow = LabWorkflow(args.data, args.output, seed=args.seed, steps=args.steps, compile_pdf=not args.no_pdf)
        if args.command == "start":
            result = workflow.start()
        elif args.command == "status":
            result = workflow.status()
        elif args.command == "message":
            result = workflow.handle_message(args.text)
        elif args.command == "choose":
            result = workflow.set_choice(args.key, args.value)
        elif args.command == "query":
            if not args.instructor:
                state = workflow.status()["state"]
                if state["completed_stage"] < 3:
                    raise WorkflowError("Complete the canonical SQL stage 3 before additional queries.")
            from cohort_lab.query import run_query
            sql = args.sql_file.read_text(encoding="utf-8") if args.sql_file else sys.stdin.read()
            result = run_query(args.data, args.output, sql, max_rows=args.max_rows, timeout_seconds=args.timeout)
        elif args.command == "validate-data":
            verify_frozen_inputs(args.data)
            from cohort_lab.data import validate_data
            result = validate_data(args.data)
        elif args.command == "batch":
            result = run_batch(args.data, args.output, seed=args.seed, steps=args.steps, compile_pdf=not args.no_pdf)
        elif args.command == "challenge-template":
            from cohort_lab.challenge import write_template
            result = {"advanced": False, **write_template(args.output)}
        elif args.command == "challenge-baseline":
            from cohort_lab.challenge import baseline_predictions
            result = {"advanced": False, **baseline_predictions(args.output)}
        elif args.command == "validate-submission":
            import pandas as pd
            from cohort_lab.analysis import validate_analysis
            from cohort_lab.challenge import prediction_grid, validate_predictions
            validate_analysis(args.output)
            grid = prediction_grid(pd.read_csv(args.output/'tables/cohort_age_summary.csv'))
            checked = validate_predictions(pd.read_csv(args.csv),grid)
            result = {"advanced": False, "status": "passed", "rows": len(checked), "future_outcomes_read": False}
        else:
            raise WorkflowError("Unknown command.")
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except (WorkflowError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "advanced": False}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
