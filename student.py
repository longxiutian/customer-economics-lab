"""Student-facing teacher: one checkpoint per explicit 'next step'."""
import argparse
import json
import sys
from pathlib import Path

from cohort_lab.student import StudentWorkflow
from cohort_lab.workflow import CHOICE_STAGES, WorkflowError


def main(argv=None):
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=root / "data")
    parser.add_argument("--output", type=Path, default=root / "outputs/student")
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--no-pdf", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start")
    commands.add_parser("status")
    message = commands.add_parser("message")
    message.add_argument("text")
    choose = commands.add_parser("choose")
    choose.add_argument("key", choices=CHOICE_STAGES)
    choose.add_argument("value")
    args = parser.parse_args(argv)
    if args.steps < 3000:
        parser.error("Use at least the released 3000-step budget.")
    lesson = StudentWorkflow(args.data, args.output, seed=args.seed, steps=args.steps, compile_pdf=not args.no_pdf)
    try:
        result = lesson.start() if args.command == "start" else lesson.status() if args.command == "status" else lesson.handle_message(args.text) if args.command == "message" else lesson.set_choice(args.key, args.value)
        print(json.dumps(result, indent=2))
        return 0
    except (WorkflowError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "advanced": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
