"""Private, append-only lab telemetry. No identity or destination comes from an LLM.

One operator-owned SQLite database per host; do not put it on shared/network storage.
The broker is the authority linking run_id to an authenticated login. This ledger
uses that server-owned run_id, not a student's name, email, or model-supplied ID.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import re
import sqlite3
import time
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def normalize_usage(raw):
    """OpenAI-compatible/vLLM counts: cache and reasoning are subsets, not extras."""
    raw = raw or {}
    def count(value):
        return value if type(value) is int and value >= 0 else None
    prompt, completion = count(raw.get("prompt_tokens")), count(raw.get("completion_tokens"))
    return {"input_tokens": prompt, "output_tokens": completion,
            "cached_input_tokens": count((raw.get("prompt_tokens_details") or {}).get("cached_tokens")),
            "reasoning_tokens": count((raw.get("completion_tokens_details") or {}).get("reasoning_tokens")),
            "total_tokens": prompt + completion if prompt is not None and completion is not None else None,
            "semantics": "openai_vllm_cache_and_reasoning_are_subsets", "raw": raw or None}


class Telemetry:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL, kind TEXT NOT NULL, happened_at REAL NOT NULL,
                    received_at REAL NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_scope ON events(session_id,run_id,seq);
                CREATE TRIGGER IF NOT EXISTS immutable_event_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'telemetry events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_event_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'telemetry events are append-only'); END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, *, event_id, run_id, session_id, kind, happened_at, payload):
        if not all(isinstance(x, str) and 0 < len(x) <= 180 for x in (event_id, run_id, session_id, kind)):
            raise ValueError("Invalid telemetry identifiers")
        body = {"run_id": run_id, "session_id": session_id, "kind": kind,
                "happened_at": happened_at, "payload": payload}
        digest = sha(body)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT digest FROM events WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if prior["digest"] != digest:
                    raise ValueError("Conflicting telemetry replay")
                return False
            db.execute("INSERT INTO events(event_id,run_id,session_id,kind,happened_at,received_at,payload,digest) VALUES(?,?,?,?,?,?,?,?)",
                       (event_id, run_id, session_id, kind, happened_at, time.time(), canonical(payload), digest))
        return True

    def ingest_receipt(self, receipt, *, session_id):
        """Import live or archived CPU receipts idempotently. These are API messages,
        not a verified transcript of all native BlueChip chat turns.
        """
        run, job = receipt["run_id"], receipt["job_id"]
        payload = receipt["payload"]
        self.append(event_id="cpu-request:" + job, run_id=run, session_id=session_id,
                    kind="lab_request", happened_at=receipt["started_at"],
                    payload={"request_id": job, "action": payload["action"],
                             "message": payload.get("message"), "sql": payload.get("sql"),
                             "choice_key": payload.get("key"), "choice_value": payload.get("value"),
                             "source": "lab_api_received", "verbatim_platform_transcript": False,
                             "checkpoint_before": receipt.get("expected_step")})
        if receipt["status"] == "started":
            return
        result = receipt.get("result") or {}
        packet = result.get("packet") or {}
        self.append(event_id="cpu-terminal:" + job, run_id=run, session_id=session_id,
                    kind="checkpoint", happened_at=receipt["finished_at"],
                    payload={"request_id": job, "outcome": receipt["status"],
                             "step": receipt.get("step_after", packet.get("step")),
                             "fresh_fit": receipt.get("fresh_fit", False),
                             "calculation_seconds": max(0, receipt.get("calculation_finished_at", receipt["finished_at"]) - receipt["started_at"]),
                             "validated": packet.get("validation", {}).get("valid"),
                             "artifacts": [{"name": a["name"], "sha256": a["sha256"]} for a in packet.get("artifacts", [])]})
        model = packet.get("interpretation") or {}
        if model.get("status") == "completed":
            attempt = model.get("router_attempt_id") or model.get("response_id") or "legacy:" + job
            self.append(event_id="receipt-model:" + job, run_id=run, session_id=session_id,
                        kind="inference_receipt", happened_at=model.get("finished_at", receipt["finished_at"]),
                        payload={"request_id": job, "attempt_id": attempt, "model": model.get("model"),
                                 "model_revision": model.get("revision"), "replica_id": model.get("replica_id"),
                                 "response_id": model.get("response_id"), "outcome": "completed",
                                 "usage": normalize_usage(model.get("usage")),
                                 "inference_seconds": max(0, model.get("finished_at", 0) - model.get("started_at", 0)),
                                 "text": model.get("text", ""), "source": "provider_completion_receipt"})
        elif model:
            self.append(event_id="receipt-model:" + job, run_id=run, session_id=session_id,
                        kind="inference_receipt", happened_at=receipt["finished_at"],
                        payload={"request_id": job, "attempt_id": "legacy-unknown:" + job,
                                 "outcome": "unknown", "usage": normalize_usage(None),
                                 "source": "worker_reported_unavailable; dispatch_not_known"})

    def events(self, run_id, session_id, *, cutoff_seq=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE run_id=? AND session_id=? AND seq<=? ORDER BY seq",
                              (run_id, session_id, cutoff_seq or 2**63 - 1)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


def redact(text, *, private_terms=()):
    text = str(text)
    for term in sorted(private_terms, key=len, reverse=True):
        if term:
            text = re.sub(re.escape(term), "[private identity]", text, flags=re.I)
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)\b(?:api[_ -]?key|token|password|secret)\s*[:=]\s*[^\s,;]+", "credential=[redacted]", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[email]", text)
    text = re.sub(r"https?://[^\s<>\"']+", "[link]", text)
    text = re.sub(r"(?i)\b[A-Z]:[\\/][^\r\n\"<>]+", "[local path]", text)
    text = re.sub(r"/(?:home|Users|mnt|workspaces)/[^\s\"<>]+", "[private path]", text)
    text = re.sub(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", "[identifier]", text)
    return text
