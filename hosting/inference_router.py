"""Durable fair admission for independent Nemotron replicas.

This is the operator-side router core. It neither allocates GPUs nor exposes a
student-facing endpoint. A private authenticated transport may call submit/poll;
the invocation adapter owns tunnels and provider credentials. Deployment requires
fresh matching health attestations and a measured classroom load rehearsal.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hosting.telemetry import canonical, normalize_usage, sha


class FairRouter:
    def __init__(self, database, telemetry, replicas, *, config_hash, expires_at,
                 max_queue=128, max_per_student=4, health_ttl=30, request_deadline=150, drain_margin=15, clock=time.time):
        self.database, self.telemetry = Path(database), telemetry
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.replicas = {r["id"]: dict(r) for r in replicas}
        if not self.replicas or len(self.replicas) != len(replicas):
            raise ValueError("Supply distinct operator-owned replicas")
        if any(type(r.get("capacity")) is not int or r["capacity"] < 1 for r in replicas):
            raise ValueError("Replica capacity must be a positive measured limit")
        self.config_hash, self.expires_at = config_hash, expires_at
        self.max_queue, self.max_per_student, self.health_ttl, self.clock = max_queue, max_per_student, health_ttl, clock
        self.request_deadline, self.drain_margin = request_deadline, drain_margin
        self.health = {}
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                  run_id TEXT NOT NULL, session_id TEXT NOT NULL, payload TEXT NOT NULL,
                  digest TEXT NOT NULL, arrived REAL NOT NULL, state TEXT NOT NULL,
                  attempt_id TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS attempts (
                  id TEXT PRIMARY KEY, request_id TEXT NOT NULL, replica_id TEXT NOT NULL,
                  dispatched REAL NOT NULL, state TEXT NOT NULL, ended REAL, result TEXT);
                CREATE TABLE IF NOT EXISTS fairness(run_id TEXT PRIMARY KEY, last_seq INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES('dispatch_sequence',0);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def set_health(self, replica_id, *, revision, config_hash, manifest_hash, verified_at, expires_at, ready):
        if replica_id not in self.replicas:
            raise ValueError("Unknown replica")
        self.health[replica_id] = {"revision": revision, "config_hash": config_hash,
                                  "manifest_hash": manifest_hash, "verified_at": verified_at, "expires_at": expires_at, "ready": ready}

    def submit(self, *, request_id, run_id, session_id, payload):
        """IDs must come from a trusted broker job, never from the student text."""
        stamp = self.clock()
        if stamp + self.request_deadline + self.drain_margin >= self.expires_at:
            raise ValueError("The serving window has ended")
        digest = sha({"run_id": run_id, "session_id": session_id, "payload": payload})
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior:
                if prior["digest"] != digest:
                    raise ValueError("Conflicting request replay")
                return dict(prior)
            if db.execute("SELECT count(*) FROM requests WHERE state='queued'").fetchone()[0] >= self.max_queue:
                raise ValueError("Inference queue is full")
            if db.execute("SELECT count(*) FROM requests WHERE run_id=? AND state IN ('queued','dispatched','ambiguous')", (run_id,)).fetchone()[0] >= self.max_per_student:
                raise ValueError("This student already has the maximum pending requests")
            db.execute("INSERT INTO requests(id,run_id,session_id,payload,digest,arrived,state) VALUES(?,?,?,?,?,?,'queued')",
                       (request_id, run_id, session_id, canonical(payload), digest, stamp))
        return self.poll(request_id, run_id=run_id)

    def poll(self, request_id, *, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM requests WHERE id=? AND run_id=?", (request_id, run_id)).fetchone()
        if row is None:
            raise KeyError("Request not found in this workspace")
        result = dict(row)
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def claim(self):
        stamp = self.clock()
        if stamp + self.request_deadline + self.drain_margin >= self.expires_at:
            return None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            available = []
            for name, spec in self.replicas.items():
                h = self.health.get(name, {})
                if not (h.get("ready") and h.get("revision") == spec["revision"]
                        and h.get("config_hash") == self.config_hash
                        and h.get("manifest_hash") == spec["manifest_hash"]
                        and 0 <= stamp - h.get("verified_at", 0) <= self.health_ttl
                        and h.get("expires_at", 0) > stamp + self.request_deadline + self.drain_margin):
                    continue
                active = db.execute("SELECT count(*) FROM attempts WHERE replica_id=? AND state IN ('dispatched','ambiguous')", (name,)).fetchone()[0]
                if active < spec["capacity"]:
                    available.append((active / spec["capacity"], name))
            if not available:
                return None
            # Least recently served student; FIFO within that student's queue.
            row = db.execute("""SELECT r.* FROM requests r LEFT JOIN fairness f ON f.run_id=r.run_id
                WHERE r.state='queued' AND NOT EXISTS(SELECT 1 FROM requests a WHERE a.run_id=r.run_id
                    AND a.state IN ('dispatched','ambiguous'))
                ORDER BY COALESCE(f.last_seq,-1),r.seq LIMIT 1""").fetchone()
            if row is None:
                return None
            name, attempt = min(available)[1], str(uuid.uuid4())
            db.execute("INSERT INTO attempts(id,request_id,replica_id,dispatched,state) VALUES(?,?,?,?,'dispatched')",
                       (attempt, row["id"], name, stamp))
            db.execute("UPDATE requests SET state='dispatched',attempt_id=? WHERE id=?", (attempt, row["id"]))
            db.execute("UPDATE meta SET value=value+1 WHERE key='dispatch_sequence'")
            seq = db.execute("SELECT value FROM meta WHERE key='dispatch_sequence'").fetchone()[0]
            db.execute("INSERT INTO fairness VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET last_seq=excluded.last_seq", (row["run_id"], seq))
        return {**dict(row), "payload": json.loads(row["payload"]), "attempt_id": attempt,
                "replica_id": name, "dispatched_at": stamp, "queue_seconds": stamp - row["arrived"]}

    def finish(self, ticket, *, outcome, response=None):
        if outcome not in {"completed", "failed", "ambiguous"}:
            raise ValueError("Invalid terminal outcome")
        response = response or {}
        # Preserve the provider receipt even when an interpretation fails validation.
        result = {"outcome": outcome, "response": response,
                  "usage": normalize_usage(response.get("usage"))}
        stamp = self.clock()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=?", (ticket["attempt_id"],)).fetchone()
            if not row or row["request_id"] != ticket["id"] or row["replica_id"] != ticket["replica_id"]:
                raise ValueError("Attempt identity mismatch")
            if row["state"] != "dispatched":
                if row["result"] == canonical(result):
                    return
                raise ValueError("Terminal attempt cannot be overwritten; reconcile explicitly")
            db.execute("UPDATE attempts SET state=?,ended=?,result=? WHERE id=?", (outcome, stamp, canonical(result), row["id"]))
            db.execute("UPDATE requests SET state=?,result=? WHERE id=?", (outcome, canonical(result), row["request_id"]))
        self.export_attempts()

    def export_attempts(self):
        """Durable outbox replay repairs a crash between DB commit and ledger append."""
        with self.connect() as db:
            rows = db.execute("SELECT a.*,r.run_id,r.session_id,r.arrived FROM attempts a JOIN requests r ON r.id=a.request_id WHERE a.state!='dispatched' ORDER BY a.dispatched,a.id").fetchall()
        for row in rows:
            result = json.loads(row["result"] or "{}")
            response = result.get("response") or {}
            self.telemetry.append(event_id="router-terminal:" + row["id"] + ":" + row["state"],
                run_id=row["run_id"], session_id=row["session_id"], kind="inference_attempt",
                happened_at=row["ended"], payload={"attempt_id": row["id"], "request_id": row["request_id"],
                "outcome": row["state"], "model": response.get("model"),
                "model_revision": self.replicas[row["replica_id"]]["revision"], "replica_id": row["replica_id"],
                "queue_seconds": row["dispatched"] - row["arrived"],
                "inference_seconds": row["ended"] - row["dispatched"],
                "usage": result.get("usage", normalize_usage(None)), "source": "router_provider_attempt"})

    def recover_after_exclusive_restart(self):
        """Operator must first confirm the previous router is stopped. Never replay."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE attempts SET state='ambiguous',ended=? WHERE state='dispatched'", (self.clock(),))
            db.execute("UPDATE requests SET state='ambiguous' WHERE state='dispatched'")
        self.export_attempts()

    def reconcile(self, attempt_id, *, outcome, response, reason):
        """Private operator action after confirming the original generation ended."""
        if outcome not in {"completed", "failed"} or not reason.strip():
            raise ValueError("Reconciliation requires a terminal result and reason")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if not row or row["state"] != "ambiguous":
                raise ValueError("Only an ambiguous attempt can be reconciled")
            state = "reconciled_" + outcome
            result = {"outcome": state, "response": response, "reason": reason,
                      "usage": normalize_usage(response.get("usage"))}
            db.execute("UPDATE attempts SET state=?,ended=?,result=? WHERE id=?", (state, self.clock(), canonical(result), attempt_id))
            db.execute("UPDATE requests SET state=?,result=? WHERE id=?", (state, canonical(result), row["request_id"]))
        self.export_attempts()

    def dispatch_available(self, executor, invoke):
        """Dispatch into one owner-controlled pool; invoke must have a hard deadline."""
        futures = []
        while ticket := self.claim():
            def run(ticket=ticket):
                try:
                    result = invoke(self.replicas[ticket["replica_id"]], ticket)
                    # Adapter verifies model/revision/config and normal completion.
                    if result.get("status") != "completed":
                        self.finish(ticket, outcome="failed", response=result)
                    else:
                        self.finish(ticket, outcome="completed", response=result)
                except Exception as exc:
                    # Exception text may contain URLs or credentials; keep only its type.
                    self.finish(ticket, outcome="ambiguous", response={"error_type": type(exc).__name__})
            futures.append(executor.submit(run))
        return futures
