"""One learner-authorized teaching checkpoint over the canonical analysis engine."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .workflow import LabWorkflow, WorkflowError, implementation_snapshot, verify_frozen_inputs

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Lesson:
    title: str
    core_stage: int
    objective: str
    check: str
    files: tuple[str, ...] = ()


LESSONS = (
    Lesson("Welcome to Studio North", -1,
           "Introduce the membership business and the decision: are we moving in the right direction? Explain that eight source datasets become evidence, a recommendation, and finally a report.",
           "Explain the next step gate and invite questions. No analysis or report has been run.", ("@docs/business_brief.md",)),
    Lesson("Check the working environment", 0,
           "Verify the frozen dataset and the tools needed to run the analysis locally.",
           "Show each readiness result. Resolve a failed check before moving on."),
    Lesson("Understand the customer journey", 1,
           "Read the broad customer journey and identify where membership value or friction could arise.",
           "Which point in this journey could affect renewal? A journey hypothesis is not yet evidence.", ("diagrams/business-journey.png", "diagrams/business-journey.json")),
    Lesson("Inspect the eight source tables", 1,
           "Identify each source owner, row unit, key and relationship before joining records.",
           "Why could joining transaction and activity rows directly multiply revenue?", ("diagrams/source_inventory.json", "diagrams/source-tables.png")),
    Lesson("Classify fields using the UCV", 2,
           "Show the field tables for all eight datasets under Identifiers, Engagement, Relationship and Perception.",
           "Distinguish reported needs from behavior; explain an empty category and a contextual field.", ("diagrams/ucv-tables.md",)),
    Lesson("Propose segments and a journey hypothesis", 2,
           "Choose a baseline grouping and an outcome on which to assess homogeneity within cells and heterogeneity across cells.",
           "Save the learner's segmentation_rationale and journey_hypothesis if supplied. A descriptive grouping does not change the fitted model strata.", ("tables:raw/people.csv",)),
    Lesson("Build the cohort view with SQL", 3,
           "Trace source transactions through first paid acquisition, cohort assignment, customer-month records and cohort aggregation.",
           "Trace the first cohort's age-2 retention cell. Explain the original-customer denominator, preaggregated joins, observed zeros and unobserved future blanks. The wide pivot is presentation code.", ("@sql/01_views.sql", "tables/customer_month.csv", "tables/cohort_totals.csv")),
    Lesson("Read the retention triangle", 4,
           "Compare retention across acquisition cohorts at the same age.",
           "Point to an observed cell, a future blank and a fair comparison.", ("report/figures/cohort-retention-triangle.png",)),
    Lesson("Read the cohort cash triangle", 4,
           "Connect contribution, historical average CAC and observed cash recovery.",
           "Explain why cumulative contribution and cash after acquisition cost are different.", ("report/figures/cohort-cash-triangle.png",)),
    Lesson("Evaluate segmentation", 4,
           "Compare outcome dispersion within and across candidate cells on the same customers and horizon.",
           "Hold complexity comparable; assess remaining within-cell dispersion as well as differences between means.", ("tables/segmentation_objective.csv", "tables/segmentation_comparison.csv")),
    Lesson("Revisit journey friction", 4,
           "Compare the journey hypothesis with engagement, feedback and pre-renewal diagnostic evidence.",
           "Separate descriptive association from causation and identify missing feedback or limited comparison support.", ("report/figures/journey-cohort-diagnostics.png", "tables/friction_contrasts.csv")),
    Lesson("Connect cohorts to company economics", 4,
           "Explain how successive cohorts contribute to the company's calendar-time trajectory.",
           "Invite and save a provisional_verdict. The operating panel excludes the separate holdout research budget.", ("report/figures/company-economics.png", "tables/cohort_six_month_comparison.csv")),
    Lesson("Update iCAC with continuous holdouts", 5,
           "Describe all six monthly waves and reconcile attributed buyers with incremental buyers and acquisition cost.",
           "Use treatment minus scaled control buyers, select the latest completed test and distinguish historical average CAC. These experiments do not estimate retention or revenue.", ("tables/channel_cac.csv", "tables/channel_cac_current.csv", "report/figures/channel-icac-history.png")),
    Lesson("Understand the forecasting model", 5,
           "Explain heterogeneous churn, survivor selection, the Gamma revenue model and the separate Orduz neural benchmark before fitting.",
           "Which part of an immature cohort's value is observed, and which part requires extrapolation?", ("@docs/model-specification.md",)),
    Lesson("Fit and check the models", 6,
           "Fit the released models and inspect historical holdout validation and inference diagnostics.",
           "Distinguish in-sample fit from held-out accuracy. Discuss a weak check before trusting a forecast.", ("tables/backtest.csv", "tables/valuation_backtest.csv", "tables/orduz_benchmark.csv", "model_summary.json")),
    Lesson("Interpret value and payback", 6,
           "Separate observed contribution from forecast value and examine maturity and uncertainty.",
           "Compare customer values at the same horizon and explain observed versus forecast payback.", ("report/figures/forecast-detail.png", "tables/strategic_segment_breakout.csv")),
    Lesson("Bring acquisition cost and value together", 6,
           "Combine current iCAC with contribution value before CAC using the common mature-cohort benchmark.",
           "Subtract acquisition cost once. State the assumption about marginal customer value and explain how the next completed test changes a spending decision.", ("tables/channel_value_decision.csv", "report/figures/incremental-cash-paths.png")),
    Lesson("Make the recommendation", 6,
           "Have the learner state the company verdict, recommended action and evidence that would change it.",
           "Save their actual final_verdict and recommended_action. Discuss conflicting evidence without inventing their judgment. The report has not been compiled.", ("tables/channel_value_decision.csv", "learner_choices.json")),
    Lesson("Generate and review the report", 7,
           "Compile the report from the saved evidence and the learner's own recommendation, then inspect its layout and citations.",
           "Deliver the PDF, editable source and provenance. Explain how to reproduce it and invite follow-up questions.", ("report/customer-economics-report.tex",)),
)


class StudentWorkflow:
    def __init__(self, data_dir: Path, output_dir: Path, *, runner=None, evidence=None,
                 seed=20261116, steps=3000, compile_pdf=True):
        self.output = Path(output_dir).resolve()
        self.path = self.output / "lesson_state.json"
        self.core = LabWorkflow(data_dir, self.output, runner=runner, seed=seed,
                                steps=steps, compile_pdf=compile_pdf)
        self.evidence = evidence or self._evidence

    def _save(self, state):
        self.output.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def _load(self):
        if not self.path.exists():
            raise WorkflowError("Start the student lesson first.")
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state["implementation"] != implementation_snapshot() or state["inputs"] != verify_frozen_inputs(self.core.data_dir):
            raise WorkflowError("The lesson's frozen implementation or inputs changed. Restore the release or use a fresh output folder.")
        if self.core.state_path.exists():
            core = self.core.status()["state"]
            # Revisions/configuration changes invalidate the corresponding lessons too.
            limit = max(i for i, item in enumerate(LESSONS) if item.core_stage <= core["completed_stage"])
            if state["completed_step"] > limit:
                state["invalidations"].append({"from_step": limit + 1, "previous_step": state["completed_step"]})
                state["completed_step"] = limit
                state["results"] = {k: v for k, v in state["results"].items() if int(k) <= limit}
                self._save(state)
        return state

    def _packet(self, state, *, advanced=False, error=None):
        step = state["completed_step"]
        item = LESSONS[step]
        packet = {"advanced": advanced, "step": step, "total_steps": len(LESSONS), "title": item.title,
                  "objective": item.objective, "check": item.check,
                  "result": state["results"].get(str(step), {}),
                  "choices": json.loads((self.output / "learner_choices.json").read_text(encoding="utf-8")) if (self.output / "learner_choices.json").exists() else {},
                  "message": "Lab complete. Questions do not restart it." if step == len(LESSONS) - 1 else "Type next step to continue."}
        if error:
            packet["error"] = error
        if step == len(LESSONS) - 1:
            debrief = self.output / "debrief/latest.json"
            if debrief.is_file():
                packet["personal_debrief"] = json.loads(debrief.read_text(encoding="utf-8"))
                packet["debrief_instruction"] = "Review and personalize this separate learning debrief using its frozen evidence, then deliver it with the executive report."
        return packet

    def start(self):
        if self.path.exists():
            return self.status()
        if self.output.exists() and any(self.output.iterdir()):
            raise WorkflowError("Start a student lesson in a fresh output folder; preserve existing runs.")
        state = {"schema_version": 1, "completed_step": 0, "inputs": verify_frozen_inputs(self.core.data_dir),
                 "implementation": implementation_snapshot(), "messages": [], "invalidations": [],
                 "results": {"0": self.evidence(0)}}
        self._save(state)
        return self._packet(state, advanced=True)

    def status(self):
        return self._packet(self._load())

    def handle_message(self, message):
        state = self._load()
        explicit = message.strip().casefold() == "next step"
        state["messages"].append({"step": state["completed_step"], "text": message, "explicit_next_step": explicit})
        self._save(state)
        if not explicit or state["completed_step"] == len(LESSONS) - 1:
            return self._packet(state)
        upcoming = state["completed_step"] + 1
        target = LESSONS[upcoming].core_stage
        current = self.core.status()["state"]["completed_stage"] if self.core.state_path.exists() else -1
        if target > current:
            if target != current + 1:
                raise WorkflowError("The lesson and analysis state disagree; no stages were skipped.")
            result = self.core.start() if target == 0 and not self.core.state_path.exists() else self.core.handle_message(message)
            if not result["advanced"]:
                return self._packet(state, error={k: v for k, v in result.items() if k != "state"})
        result = self.evidence(upcoming)
        state["results"][str(upcoming)] = result
        state["completed_step"] = upcoming
        self._save(state)
        if upcoming == len(LESSONS) - 1 and (self.output / "usage/session.json").is_file():
            from .debrief import prepare
            try:
                prepare(self.output)
            except (OSError, ValueError) as exc:
                return self._packet(state, advanced=True, error={"personal_debrief": str(exc), "executive_report_preserved": True})
        return self._packet(state, advanced=True)

    def set_choice(self, key, value):
        self._load()
        if not self.core.state_path.exists():
            raise WorkflowError("Finish the readiness checkpoint before saving analytical choices.")
        if not value.strip():
            raise WorkflowError("A learner choice must contain their actual judgment.")
        self.core.set_choice(key, value)
        return self.status()

    def _evidence(self, step):
        files = []
        for relative in LESSONS[step].files:
            path = ROOT / relative[1:] if relative.startswith("@") else self.core.data_dir / relative[11:] if relative.startswith("tables:raw/") else self.output / relative
            if relative == "learner_choices.json" and not path.exists():
                continue  # Asking for a judgment never fabricates one.
            if not path.is_file():
                raise WorkflowError(f"Missing checkpoint artifact: {path}")
            entry = {"path": str(path), "kind": path.suffix.lstrip(".")}
            if path.suffix == ".csv":
                with path.open(encoding="utf-8", newline="") as source:
                    reader = csv.DictReader(source)
                    entry["columns"] = reader.fieldnames
                    rows = []
                    limit = 24 if path.name == "channel_cac.csv" else 6
                    count = 0
                    for row in reader:
                        count += 1
                        if count <= limit:
                            rows.append(row)
                    entry.update(preview=rows, row_count=count)
            files.append(entry)
        packet = {"files": files}
        if step >= 6:
            manifest_path = self.core.data_dir / "data_manifest.json"
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
            packet["data_context"] = {
                "source": "data/data_manifest.json",
                "source_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "dataset_version": manifest["dataset_version"],
                "observed_cutoff_exclusive": manifest["data_as_of"],
                "timezone": manifest["timezone"],
                "currency": manifest["currency"],
                "cohort_definition": manifest["definitions"]["cohort"],
                "observation_definition": manifest["definitions"]["time"],
            }
        if step == 1:
            packet["readiness"] = json.loads(self.core.state_path.read_text(encoding="utf-8"))["stages"]["0"]["result"]
        if step == 6:
            from .query import run_query
            sql = ("SELECT cohort_month, age_month, count(*) AS n_acquired, sum(retained) AS n_retained, "
                   "sum(retained)::DOUBLE / count(*) AS retained_share FROM customer_month "
                   "WHERE cohort_month = (SELECT min(cohort_month) FROM customer_month) AND age_month = 2 "
                   "GROUP BY cohort_month, age_month")
            receipt = run_query(self.core.data_dir, self.output, sql)
            packet["cell_trace"] = {"sql": sql, "artifacts": [str(self.output / name) for name in receipt["artifacts"]]}
        if step == len(LESSONS) - 1:
            pdf = self.output / "report/customer-economics-report.pdf"
            packet["pdf"] = str(pdf) if pdf.exists() else None
            packet["compiled_pdf"] = pdf.exists()
        return packet
