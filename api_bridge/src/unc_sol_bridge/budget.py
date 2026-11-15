"""SQLite ledger. Every dispatch is reserved atomically before HTTP; unknown charges stay held and are never reset."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .config import BridgeError

STALE_SECONDS = 900  # an in-flight row older than this belongs to a dead process; its reservation stays held
COUNTED = "CASE state WHEN 'settled' THEN charge WHEN 'released' THEN 0 ELSE reserved END"
TABLES = (
    "CREATE TABLE IF NOT EXISTS period(allocation TEXT NOT NULL, period TEXT NOT NULL, cap INTEGER NOT NULL, "
    "baseline INTEGER NOT NULL, baseline_source TEXT NOT NULL, PRIMARY KEY(allocation, period))",
    "CREATE TABLE IF NOT EXISTS calls(request_id TEXT PRIMARY KEY, allocation TEXT NOT NULL, period TEXT NOT NULL, "
    "run TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL, packet_sha TEXT NOT NULL, step INTEGER NOT NULL, "
    "input_bound INTEGER NOT NULL, max_output INTEGER NOT NULL, reserved INTEGER NOT NULL, input_tokens INTEGER, "
    "output_tokens INTEGER, charge INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '', "
    "created REAL NOT NULL, updated REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quarantine(allocation TEXT PRIMARY KEY, reason TEXT NOT NULL, created REAL NOT NULL)",
)


class BudgetBlocked(BridgeError):
    """Raised before any HTTP when a call may not be dispatched. Costs nothing."""


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._tx() as db:
            for statement in TABLES:
                db.execute(statement)

    @contextmanager
    def _tx(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def open_period(self, allocation, period, cap, baseline, source):
        with self._tx() as db:
            newest = db.execute("SELECT MAX(period) FROM period WHERE allocation=?", (allocation,)).fetchone()[0]
            if newest and period < newest:
                raise BudgetBlocked("period_regressed", f"A later period ({newest}) is already recorded for this allocation.")
            row = db.execute("SELECT baseline FROM period WHERE allocation=? AND period=?", (allocation, period)).fetchone()
            if row and baseline < row["baseline"]:
                raise BudgetBlocked("baseline_reset_refused", "The recorded baseline is higher. Spent or unknown allocation is never reset.",
                                    recorded_baseline=row["baseline"])
            db.execute("INSERT INTO period VALUES(?,?,?,?,?) ON CONFLICT(allocation, period) DO UPDATE SET "
                       "cap=excluded.cap, baseline=excluded.baseline, baseline_source=excluded.baseline_source",
                       (allocation, period, cap, baseline, source))

    def _snapshot(self, db, allocation, period, stage):
        row = db.execute("SELECT cap, baseline, baseline_source FROM period WHERE allocation=? AND period=?", (allocation, period)).fetchone()
        if row is None:
            raise BudgetBlocked("period_unopened", "No baseline is recorded for this allocation and period.")
        sums = db.execute(
            "SELECT COALESCE(SUM(CASE WHEN state='settled' THEN charge ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN state IN ('inflight','held') THEN reserved ELSE 0 END),0), "
            f"COALESCE(SUM(CASE WHEN stage=? THEN {COUNTED} ELSE 0 END),0) FROM calls WHERE allocation=? AND period=?",
            (stage, allocation, period)).fetchone()
        quarantine = db.execute("SELECT reason FROM quarantine WHERE allocation=?", (allocation,)).fetchone()
        return {"allocation_cap": row["cap"], "baseline": row["baseline"], "baseline_source": row["baseline_source"],
                "settled": sums[0], "outstanding": sums[1], "stage_used": sums[2],
                "remaining": row["cap"] - row["baseline"] - sums[0] - sums[1], "quarantine": quarantine["reason"] if quarantine else None}

    def snapshot(self, allocation, period, stage):
        with self._tx() as db:
            return self._snapshot(db, allocation, period, stage)

    def reserve(self, *, request_id, allocation, period, run, stage, stage_cap, single_call, packet_sha, step, input_bound, max_output):
        reserved, now = input_bound + max_output, time.time()
        # An admission denial must not roll this reconciliation back to "inflight".
        # The charge remains identical in either state.
        with self._tx() as db:
            db.execute("UPDATE calls SET state='held', detail='orphaned in flight; charge unknown', updated=? "
                       "WHERE state='inflight' AND created<?", (now, now - STALE_SECONDS))
        with self._tx() as db:
            view = self._snapshot(db, allocation, period, stage)
            if view["quarantine"]:
                raise BudgetBlocked("quarantined", "This allocation is quarantined until an operator reviews it.", reason=view["quarantine"])
            if db.execute("SELECT 1 FROM calls WHERE request_id=?", (request_id,)).fetchone():
                raise BudgetBlocked("duplicate_request_id", "This request_id was already used. Calls are never replayed.")
            if db.execute("SELECT 1 FROM calls WHERE run=? AND state='inflight'", (run,)).fetchone():
                raise BudgetBlocked("call_in_flight", "Another Sol call for this run is still in flight.")
            if single_call and db.execute("SELECT 1 FROM calls WHERE allocation=? AND stage=? AND state!='released'",
                                          (allocation, stage)).fetchone():
                raise BudgetBlocked("startup_call_already_used", "The startup phase allows one dispatch for this allocation, and it was used.")
            if db.execute("SELECT 1 FROM calls WHERE run=? AND state='held'", (run,)).fetchone():
                raise BudgetBlocked("charge_held", "An earlier call for this run has unknown usage. Review its receipt before another dispatch.")
            view = self._snapshot(db, allocation, period, stage)
            facts = {"needed": reserved, "remaining": view["remaining"], "stage_used": view["stage_used"], "stage_cap": stage_cap}
            if reserved > view["remaining"]:
                raise BudgetBlocked("allocation_cap", "Baseline, settled and outstanding usage plus this call would exceed the allocation.", **facts)
            if view["stage_used"] + reserved > stage_cap:
                raise BudgetBlocked("stage_cap", "This call would exceed the cap for the current phase.", **facts)
            db.execute("INSERT INTO calls(request_id, allocation, period, run, stage, state, packet_sha, step, input_bound, max_output, "
                       "reserved, created, updated) VALUES(?,?,?,?,?,'inflight',?,?,?,?,?,?,?)",
                       (request_id, allocation, period, run, stage, packet_sha, step, input_bound, max_output, reserved, now, now))
        return reserved

    def finish(self, request_id, state, *, input_tokens=None, output_tokens=None, total_tokens=None, detail="", quarantine=None):
        """settled = known usage (charge is inclusive, never double counted); held = dispatched, unknown; released = never sent."""
        now = time.time()
        with self._tx() as db:
            row = db.execute("SELECT allocation, input_bound, max_output FROM calls WHERE request_id=? AND state IN ('inflight','held')",
                             (request_id,)).fetchone()
            if row is None:
                raise BridgeError("ledger_conflict", "This call is not awaiting settlement.")
            charge = 0
            if state == "settled":
                charge = max(input_tokens + output_tokens, total_tokens or 0)
                if input_tokens > row["input_bound"] or output_tokens > row["max_output"] or charge > row["input_bound"] + row["max_output"]:
                    quarantine = quarantine or "actual usage exceeded the reserved bound; the byte-bound assumption needs review"
            db.execute("UPDATE calls SET state=?, input_tokens=?, output_tokens=?, charge=?, detail=?, updated=? WHERE request_id=?",
                       (state, input_tokens, output_tokens, charge, detail, now, request_id))
            if quarantine:
                db.execute("INSERT OR IGNORE INTO quarantine VALUES(?,?,?)", (row["allocation"], quarantine, now))

    def get(self, request_id):
        with self._tx() as db:
            row = db.execute("SELECT * FROM calls WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None
