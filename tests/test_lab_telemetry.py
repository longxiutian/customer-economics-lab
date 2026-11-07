"""Behavioral checks for login-scoped usage, fair routing, and personal feedback."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hosting.inference_router import FairRouter
from hosting.student_debrief import DeliveryOutbox, freeze, provider_packet, validate_response, RUBRIC_VERSION
from hosting.telemetry import Telemetry, normalize_usage, redact


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Telemetry(self.root / "events.sqlite")
        self.addCleanup(self.tmp.cleanup)

    def event(self, event_id="a", run="student-a", payload=None):
        return self.ledger.append(event_id=event_id, run_id=run, session_id="class-1", kind="lab_request", happened_at=10,
            payload=payload or {"action": "message", "message": "Which assumptions should I check?", "source": "lab_api_received"})

    def test_replayed_callback_once_and_conflicts_rejected(self):
        self.assertTrue(self.event())
        self.assertFalse(self.event())
        with self.assertRaises(ValueError):
            self.event(run="student-b")
        self.assertEqual(len(self.ledger.events("student-a", "class-1")), 1)
        with self.ledger.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE events SET payload='{}'")

    def test_token_subsets_and_missing_counts(self):
        usage = normalize_usage({"prompt_tokens": 100, "completion_tokens": 40, "prompt_tokens_details": {"cached_tokens": 20}, "completion_tokens_details": {"reasoning_tokens": 5}})
        self.assertEqual(usage["total_tokens"], 140)
        self.assertIsNone(normalize_usage(None)["total_tokens"])
        self.assertIsNone(normalize_usage({"prompt_tokens": True})["input_tokens"])

    def test_scope_freeze_and_private_fields(self):
        self.event()
        self.event("foreign", run="student-b", payload={"action": "message", "message": "OTHER STUDENT SECRET", "source": "lab_api_received"})
        snap = freeze(self.ledger, run_id="student-a", session_id="class-1", path=self.root / "a.json")
        self.event("late")
        same = freeze(self.ledger, run_id="student-a", session_id="class-1", path=self.root / "a.json")
        self.assertEqual(snap, same)
        exported = json.dumps(provider_packet(snap))
        self.assertNotIn("student-a", exported)
        self.assertNotIn("OTHER STUDENT SECRET", exported)
        self.assertIsNone(snap["metrics"]["native_bluechip_tokens"])
        with self.assertRaises(ValueError):
            freeze(self.ledger, run_id="student-b", session_id="class-1", path=self.root / "a.json")

    def test_unknown_attempt_not_zero(self):
        self.event()
        self.ledger.append(event_id="u", run_id="student-a", session_id="class-1", kind="inference_attempt", happened_at=12,
            payload={"attempt_id": "attempt1", "request_id": "a", "outcome": "ambiguous", "usage": normalize_usage(None)})
        snap = freeze(self.ledger, run_id="student-a", session_id="class-1", path=self.root / "a.json")
        self.assertIsNone(snap["metrics"]["nemotron_total_tokens"])
        self.assertEqual(snap["metrics"]["nemotron_attempts_with_unknown_usage"], 1)

    def test_redaction_corpus(self):
        source = 'Jane Doe jane@unc.edu https://example.edu/a?signature=secret Bearer abc123 token=private C:\\Users\\Jane\\record.json'
        clean = redact(source, private_terms=["Jane Doe"])
        for secret in ("Jane Doe", "jane@", "signature", "abc123", "private C:", "record.json"):
            self.assertNotIn(secret, clean)

    def test_foreign_citations_and_fabricated_quote_rejected(self):
        self.event()
        snap = freeze(self.ledger, run_id="student-a", session_id="class-1", path=self.root / "a.json")
        ev = snap["evidence"][1]["id"]
        response = {"rubric_version": RUBRIC_VERSION, "snapshot_id": snap["snapshot_id"],
            "observations": [{"text": "You asked about assumptions.", "evidence_ids": [ev], "quote": "assumptions"}] * 2,
            "studio_north_next_steps": [{"text": "Inspect the model.", "prompt": "Show the assumptions.", "evidence_ids": [ev]}] * 2,
            "ai_learning_next_steps": [{"text": "Check a claim.", "prompt": "Trace a claim to a source.", "evidence_ids": [ev]}] * 2}
        self.assertTrue(validate_response(snap, response))
        wrong = copy.deepcopy(response)
        wrong["observations"][0]["evidence_ids"] = ["another-student/evidence"]
        with self.assertRaises(ValueError):
            validate_response(snap, wrong)
        wrong = copy.deepcopy(response)
        wrong["observations"][0]["quote"] = "I proved all assumptions"
        with self.assertRaises(ValueError):
            validate_response(snap, wrong)

    def test_delivery_uncertain_never_reclaimed(self):
        box = DeliveryOutbox(self.root / "private-routing.sqlite")
        args = dict(session_id="class-1", recipient_key="verified-a", channel="private_download", recipient="run-a", snapshot_id="snap1", artifact_path="debrief.html")
        key = box.enqueue(**args)
        self.assertEqual(box.enqueue(**args), key)
        self.assertIsNotNone(box.claim(key))
        box.finish(key, state="uncertain", receipt={"reason": "timeout after send"})
        self.assertIsNone(box.claim(key))
        with self.assertRaises(ValueError):
            box.enqueue(**{**args, "recipient": "student-b"})


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.time = 1000.0
        self.ledger = Telemetry(self.root / "events.sqlite")
        self.replicas = [{"id": f"gpu-{i}", "revision": "pinned", "manifest_hash": "full-manifest", "capacity": 1} for i in range(4)]
        self.router = FairRouter(self.root / "queue.sqlite", self.ledger, self.replicas, config_hash="profile", expires_at=3000, clock=lambda: self.time)
        for r in self.replicas:
            self.router.set_health(r["id"], revision="pinned", config_hash="profile", manifest_hash="full-manifest", verified_at=1000, expires_at=3000, ready=True)

    def submit(self, key, run):
        return self.router.submit(request_id=key, run_id=run, session_id="class", payload={"question": key})

    def test_four_replicas_independent_and_one_active_per_student(self):
        for i in range(4):
            self.submit("a" + str(i), "A")
        for name in "BCD":
            self.submit(name, name)
        tickets = [self.router.claim() for _ in range(4)]
        self.assertEqual({t["run_id"] for t in tickets}, set("ABCD"))
        self.assertEqual(len({t["replica_id"] for t in tickets}), 4)
        self.assertIsNone(self.router.claim())
        for ticket in tickets:
            self.router.finish(ticket, outcome="completed", response={"usage": {"prompt_tokens": 5, "completion_tokens": 3}})
        self.submit("E", "E")
        self.assertEqual(self.router.claim()["run_id"], "E")

    def test_queue_isolation_idempotence_and_conflict(self):
        self.submit("id", "A")
        self.submit("id", "A")
        with self.assertRaises(ValueError):
            self.submit("id", "B")
        with self.assertRaises(KeyError):
            self.router.poll("id", run_id="B")

    def test_restart_preserves_queue_and_holds_uncertain_dispatch(self):
        self.submit("id1", "A")
        self.submit("id2", "A")
        ticket = self.router.claim()
        self.router.recover_after_exclusive_restart()
        self.assertEqual(self.router.poll("id1", run_id="A")["state"], "ambiguous")
        self.assertIsNone(self.router.claim())
        self.router.reconcile(ticket["attempt_id"], outcome="failed", response={}, reason="Operator confirmed upstream ended")
        self.assertEqual(self.router.claim()["id"], "id2")
        events = self.ledger.events("A", "class")
        self.assertEqual([e["payload"]["outcome"] for e in events], ["ambiguous", "reconciled_failed"])

    def test_stale_wrong_or_expiring_replicas_not_selected(self):
        self.submit("id", "A")
        self.router.health["gpu-0"]["revision"] = "wrong"
        self.router.health["gpu-1"]["verified_at"] = 900
        self.router.health["gpu-2"]["expires_at"] = 1050
        self.router.health["gpu-3"]["manifest_hash"] = "wrong"
        self.assertIsNone(self.router.claim())

    def test_completion_replay_and_crash_between_stores(self):
        self.submit("id", "A")
        ticket = self.router.claim()
        result = {"usage": {"prompt_tokens": 5, "completion_tokens": 3}}
        self.router.finish(ticket, outcome="completed", response=result)
        self.router.finish(ticket, outcome="completed", response=result)
        self.router.export_attempts()
        self.assertEqual(len(self.ledger.events("A", "class")), 1)


if __name__ == "__main__":
    unittest.main()
