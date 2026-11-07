"""Transport-independent BlueChip adapter over the released student workflow.

Only an instructor-owned worker calls this module. It accepts no filesystem,
shell, model endpoint, sampling-budget, or source-directory arguments from users.
"""
from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import mimetypes
import re
import time
from pathlib import Path

from .student import StudentWorkflow
from .workflow import CHOICE_STAGES, WorkflowError, implementation_snapshot, verify_frozen_inputs

API_VERSION = "studio-north-bluechip/1"
ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{8,80}$")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def release_manifest():
    inputs = verify_frozen_inputs(ROOT / "data")
    implementation = implementation_snapshot()
    return {"api_version": API_VERSION, "release_hash": digest({"inputs": inputs, "implementation": implementation}),
            "inputs": inputs, "implementation": implementation, "seed": 20261116, "steps": 3000,
            "fit_backend": "CPU float64; four sequential NUTS chains", "report_variant": "B"}


class HostedLesson:
    def __init__(self, runtime: Path, *, lesson_factory=StudentWorkflow, interpreter=None):
        self.runtime = Path(runtime).resolve()
        self.lesson_factory, self.interpreter = lesson_factory, interpreter

    def locations(self, run_id):
        if not isinstance(run_id, str) or not IDENTIFIER.fullmatch(run_id):
            raise WorkflowError("Invalid run identifier.")
        base = self.runtime / "workspaces" / run_id
        return base, base / "lesson", base / "receipts"

    @contextlib.contextmanager
    def lock(self, base):
        base.mkdir(parents=True, exist_ok=True)
        path = base / "execution.lock"
        try:
            handle = path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise WorkflowError("This workspace is already executing or requires operator recovery; no work was repeated.") from exc
        try:
            with handle:
                handle.write(str(time.time()))
            yield
        finally:
            path.unlink(missing_ok=True)

    def execute(self, job):
        job_id, run_id = job["id"], job["run_id"]
        if not IDENTIFIER.fullmatch(job_id):
            raise WorkflowError("Invalid job identifier.")
        base, output, receipts = self.locations(run_id)
        request_hash = digest(job["payload"])
        receipt_path = receipts / (job_id + ".json")
        with self.lock(base):
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt["request_hash"] != request_hash:
                    raise WorkflowError("An idempotency key was reused for different work.")
                if receipt["status"] == "completed":
                    return receipt["result"]
                raise WorkflowError("Previous execution is incomplete or uncertain; operator recovery is required before a retry.")
            manifest = release_manifest()
            if job["release_hash"] != manifest["release_hash"]:
                raise WorkflowError("The worker does not match this lab's pinned release.")
            receipt = {"job_id": job_id, "run_id": run_id, "request_hash": request_hash,
                       "release_hash": manifest["release_hash"], "started_at": time.time(), "status": "started",
                       "payload": job["payload"], "expected_step": job["checkpoint"]}
            write_json(receipt_path, receipt)
            lesson = self.lesson_factory(ROOT / "data", output, seed=20261116, steps=3000, compile_pdf=True)
            try:
                payload, action = job["payload"], job["payload"]["action"]
                before = lesson.status()["step"] if lesson.path.exists() else -1
                if before != job["checkpoint"]:
                    raise WorkflowError("Saved checkpoint differs from the queued request; no transition was attempted.")
                if action == "start":
                    packet = lesson.start()
                elif action == "message":
                    packet = lesson.handle_message(self._text(payload, "message"))
                elif action == "choose":
                    message, value = self._text(payload, "message"), self._text(payload, "value")
                    if payload.get("key") not in CHOICE_STAGES or value not in message:
                        raise WorkflowError("Save an allowed judgment quoted verbatim from the learner's message.")
                    packet = lesson.set_choice(payload["key"], value)
                elif action == "query":
                    if before < 6:
                        raise WorkflowError("SQL exploration becomes available after the cohort construction checkpoint.")
                    from .query import run_query
                    query = run_query(ROOT / "data", output, self._text(payload, "sql"), max_rows=500, timeout_seconds=15)
                    packet = lesson.status()
                    packet["query"] = query
                elif action == "interpret":
                    packet = lesson.status()
                elif action == "validate":
                    packet = lesson.status()
                    packet["validation"] = self.validate(output, receipts, packet)
                else:
                    raise WorkflowError("Unknown lab operation.")
                # Publish only artifacts from this checkpoint's allowlisted evidence.
                packet = self.evidence_packet(packet, output)
                receipt["calculation_finished_at"] = time.time()
                receipt["step_after"] = packet["step"]
                receipt["fresh_fit"] = before == 13 and packet["step"] == 14 and packet.get("advanced") is True
                if receipt["fresh_fit"]:
                    receipt["model_outputs"] = self.model_hashes(output)
                # CPU progress survives an unavailable model. Never label fallback prose Nemotron.
                if self.interpreter and action in {"start", "message", "interpret"}:
                    try:
                        packet["interpretation"] = self.interpreter(packet, payload.get("message", "Introduce this checkpoint."))
                    except Exception as exc:
                        packet["interpretation"] = {"status": "unavailable", "error_type": type(exc).__name__,
                                                    "message": "Nemotron did not return an interpretation. The computed checkpoint is saved."}
                if packet["step"] == 18:
                    packet["validation"] = self.validate(output, receipts, packet)
                result = {"api_version": API_VERSION, "run_id": run_id, "job_id": job_id,
                          "release_hash": manifest["release_hash"], "packet": packet,
                          "execution": {k: receipt[k] for k in ("started_at", "calculation_finished_at", "fresh_fit")},
                          "finished_at": time.time()}
                receipt.update(status="completed", finished_at=result["finished_at"], result=result)
                write_json(receipt_path, receipt)
                write_json(base / "release.json", manifest)
                return result
            except Exception as exc:
                receipt.update(status="failed", finished_at=time.time(), error_type=type(exc).__name__, error=str(exc))
                write_json(receipt_path, receipt)
                raise

    @staticmethod
    def _text(payload, key):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 12000:
            raise WorkflowError(f"Supply nonempty {key} text of at most 12,000 characters.")
        return value

    @staticmethod
    def model_hashes(output):
        paths = [output / "model_summary.json", output / "model_manifest.json", output / "posterior_draws.json"]
        paths += list((output / "model").rglob("*")) if (output / "model").exists() else []
        paths += list(output.glob("*.npz"))
        return {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths if p.is_file()}

    def evidence_packet(self, packet, output):
        packet = json.loads(json.dumps(packet))
        artifacts = []
        known = set()
        allowed_source = {ROOT / "docs/business_brief.md", ROOT / "docs/model-specification.md", ROOT / "sql/01_views.sql", ROOT / "data/people.csv"}

        def register(value):
            path = Path(value).resolve()
            if not path.is_file() or path in known:
                return None
            if not path.is_relative_to(output) and path not in allowed_source:
                raise WorkflowError("An artifact is outside the current workspace or released lesson sources.")
            if path.is_relative_to(output / "invalidated"):
                raise WorkflowError("An invalidated artifact cannot be published.")
            if path.suffix.lower() not in {".png", ".pdf", ".csv", ".json", ".md", ".tex", ".sql"}:
                return None
            known.add(path)
            data = path.read_bytes()
            label = path.relative_to(output).as_posix() if path.is_relative_to(output) else "source/" + path.relative_to(ROOT).as_posix()
            entry = {"artifact_id": hashlib.sha256((label + hashlib.sha256(data).hexdigest()).encode()).hexdigest(),
                     "name": label, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                     "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                     "local_path": str(path)}
            if path.suffix in {".md", ".sql"} and len(data) < 65000:
                entry["text"] = data.decode("utf-8")
            elif path.suffix == ".json" and len(data) < 32000:
                entry["text"] = data.decode("utf-8")
            if path.suffix == ".png" and (output / "report/chart_manifest.json").is_file():
                chart_manifest = json.loads((output / "report/chart_manifest.json").read_text(encoding="utf-8"))
                exhibit = chart_manifest.get("figures", {}).get(path.stem)
                if exhibit:
                    entry["computed_evidence"] = {k: exhibit[k] for k in ("sources", "notes", "display_values") if k in exhibit}
                    # Text inference can inspect the numerical provenance of a displayed image.
                    # A bounded preview is labeled as such; the complete chart remains downloadable.
                    if "display_values" not in exhibit:
                        previews = []
                        for source in exhibit.get("sources", [])[:2]:
                            table = output / "tables" / source
                            if table.is_file() and table.suffix == ".csv":
                                with table.open(encoding="utf-8", newline="") as stream:
                                    rows = list(csv.DictReader(stream))
                                previews.append({"source": source, "row_count": len(rows), "preview_first_rows": rows[:8]})
                        entry["computed_evidence"]["table_previews"] = previews
            if path.suffix == ".csv":
                with path.open(encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    preview, count = [], 0
                    for row in reader:
                        count += 1
                        if len(preview) < (24 if path.name == "channel_cac.csv" else 8):
                            preview.append(row)
                    entry.update(columns=reader.fieldnames, preview=preview, row_count=count)
            artifacts.append(entry)
            return {"artifact_id": entry["artifact_id"], "name": label}

        def scrub(value, key=""):
            if isinstance(value, dict):
                return {k: scrub(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [scrub(v, key) for v in value]
            if isinstance(value, str):
                if key in {"path", "pdf"} or (key == "artifacts" and len(value) < 300):
                    candidate = Path(value)
                    if not candidate.is_absolute():
                        candidate = output / candidate
                    if candidate.is_file():
                        return register(candidate)
                return value.replace(str(output), "<workspace>").replace(str(ROOT), "<release>")
            return value

        packet = scrub(packet)
        if packet["step"] == 18:
            for name in ("report/customer-economics-report.pdf", "report/customer-economics-report.tex", "implementation_manifest.json", "model_summary.json", "model_manifest.json", "learner_choices.json"):
                register(output / name)
        packet["artifacts"] = artifacts
        return packet

    def validate(self, output, receipts, packet):
        fits = []
        for path in receipts.glob("*.json"):
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("status") == "completed" and item.get("fresh_fit"):
                fits.append(item)
        current_models = self.model_hashes(output)
        fits = [f for f in fits if f.get("model_outputs") == current_models and current_models]
        choices = packet.get("choices", {})
        pdf = output / "report/customer-economics-report.pdf"
        checks = {"all_checkpoints": packet["step"] == 18,
                  "learner_verdict": bool(choices.get("final_verdict", "").strip()),
                  "learner_action": bool(choices.get("recommended_action", "").strip()),
                  "fresh_fit_receipt": bool(fits), "pdf_exists": pdf.is_file(),
                  "editable_source": (output / "report/customer-economics-report.tex").is_file()}
        pages = None
        if pdf.is_file():
            from pypdf import PdfReader
            reader = PdfReader(pdf)
            pages = len(reader.pages)
            checks["readable_pdf"] = pages >= 15 and "Studio North" in (reader.pages[0].extract_text() or "")
        return {"workflow_complete": all(checks.values()), "checks": checks, "pdf_pages": pages,
                "fit_job_ids": [f["job_id"] for f in fits], "visual_review": "not performed by this automated receipt"}
