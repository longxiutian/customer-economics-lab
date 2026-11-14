"""Bridge service: validate, compile, guard, one dispatch, settle, local receipt. Shared by the MCP server and CLI."""
from __future__ import annotations

import hashlib
import json
import re
import time

from .budget import Ledger
from .client import SolClient, endpoint_ready
from .config import EFFORT, MAX_OUTPUT_TOKENS, MODEL, BridgeConfig, BridgeError
from .credentials import describe, load_key
from .packets import INTENTS, compile_packet, load_lessons, load_state, source_fingerprint

REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
FIELDS = {"request_id": str, "intent": str, "learner_text": str, "artifact_ids": list, "note": str}
GUIDANCE = {
    "completed": "Show text to the learner unchanged, then wait for them.",
    "stale_checkpoint": "The checkpoint changed while Sol was answering. The reply is saved locally but is not current.",
    "incomplete": "Sol hit the output ceiling. No partial answer is delivered and usage is settled. Report it; do not retry on your own.",
    "refused": "Sol declined. Show the refusal text and wait.",
}
HALT = "No answer was delivered. Do not retry, rotate keys or answer as Sol yourself. Report this result and wait."


def failure(error: BridgeError) -> dict:
    return {"ok": False, "kind": error.kind, "message": error.message, "provider_called": False, "charge": "none", **error.facts}


def _arguments(raw, allowed, required) -> dict:
    if not isinstance(raw, dict) or set(raw) - set(allowed) or set(required) - set(raw):
        raise BridgeError("invalid_arguments", f"Accepted fields: {sorted(allowed)}; required: {sorted(required)}. "
                          "There is no model, prompt, system, checkpoint or file-content input.")
    for key, value in raw.items():
        listed = key == "artifact_ids" and type(value) is list and len(value) <= 12 and all(isinstance(i, str) and len(i) <= 200 for i in value)
        if type(value) is not FIELDS[key] or (key == "artifact_ids" and not listed):
            raise BridgeError("invalid_arguments", f"{key} has the wrong type or size.")
    if "request_id" in raw and not REQUEST_ID.fullmatch(raw["request_id"]):
        raise BridgeError("invalid_arguments", "request_id must be 8-64 characters of letters, digits, _ or -.")
    if "intent" in raw and raw["intent"] not in INTENTS:
        raise BridgeError("invalid_arguments", f"intent must be one of {list(INTENTS)}.")
    return {"learner_text": "", "artifact_ids": [], "note": "", **raw}


def _atomic(path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


class Bridge:
    def __init__(self, config: BridgeConfig, *, api_key=None, transport=None, url=None):
        self.config = config
        self.ledger = Ledger(config.state_dir / "budget.sqlite3")
        self._key, self._transport, self._url = api_key, transport, url
        self.run_id = hashlib.sha256(str(config.run_dir).encode("utf-8")).hexdigest()[:16]
        self.local = config.run_dir / "sol_bridge"  # created only after the lesson exists, so a fresh run folder stays fresh

    def _budget(self) -> dict:
        c = self.config
        self.ledger.open_period(c.subscription_label, c.period_id, c.allocation_cap, c.baseline_tokens, c.baseline_source)
        return dict(self.ledger.snapshot(c.subscription_label, c.period_id, c.phase), stage=c.phase, stage_cap=c.stage_cap, period_id=c.period_id)

    def _checkpoint(self) -> dict:
        lessons = load_lessons(self.config.source_root)
        if source_fingerprint(self.config.source_root, lessons) != self.config.source_fingerprint:
            raise BridgeError("source_fingerprint_mismatch", "Lesson sources differ from the fingerprint pinned in the bridge configuration.")
        state, _ = load_state(self.config, lessons)
        return {"step": state["completed_step"], "last": len(lessons) - 1, "title": lessons[state["completed_step"]].title}

    def _current_step(self):
        try:
            return self._checkpoint()["step"]
        except BridgeError:
            return None

    def status(self) -> dict:
        """Local facts only. Never loads the key and never contacts the provider."""
        c = self.config
        payload = {"ok": True, "kind": "status", "provider_called": False, "model": MODEL, "effort": EFFORT,
                   "max_output_tokens": MAX_OUTPUT_TOKENS, "phase": c.phase, "packet_max_bytes": c.packet_max_bytes,
                   "endpoint_pinned": endpoint_ready(self._url), "credential": describe(c.credential_ref), "problems": []}
        for name, probe in (("checkpoint", self._checkpoint), ("budget", self._budget)):
            try:
                payload[name] = probe()
            except BridgeError as error:
                payload["problems"].append({"kind": error.kind, "message": error.message})
        return payload

    def preview(self, raw) -> dict:
        args = _arguments(raw, ("intent", "learner_text", "artifact_ids", "note"), ("intent",))
        packet = compile_packet(self.config, args["intent"], args["learner_text"], args["artifact_ids"], args["note"])
        budget, needed = self._budget(), packet.input_bound + MAX_OUTPUT_TOKENS
        fits = budget["quarantine"] is None and needed <= budget["remaining"] and budget["stage_used"] + needed <= self.config.stage_cap
        return {"ok": True, "kind": "preview", "provider_called": False, "packet": packet.manifest | {"sha256": packet.sha256},
                "reservation_tokens": needed, "fits_token_caps": fits, "budget": budget}

    def receipt(self, raw) -> dict:
        args = _arguments(raw, ("request_id",), ("request_id",))
        row = self.ledger.get(args["request_id"])
        if row is None or row["run"] != self.run_id:
            raise BridgeError("unknown_request", "No call with this request_id exists for this run.")
        return {"ok": True, "kind": "receipt", "provider_called": False, "ledger": row, "receipt": self._read_receipt(args["request_id"])}

    async def ask(self, raw) -> dict:
        try:
            args = _arguments(raw, tuple(FIELDS), ("request_id", "intent"))
            request_id, c = args["request_id"], self.config
            row = self.ledger.get(request_id)
            if row is not None:
                return self._resume(row)
            if c.phase == "startup" and args["intent"] != "open":
                raise BridgeError("startup_opening_only", "The startup phase permits exactly one opening call and nothing else.")
            packet = compile_packet(c, args["intent"], args["learner_text"], args["artifact_ids"], args["note"])
            if not endpoint_ready(self._url):
                raise BridgeError("endpoint_unpinned", "This release has no pinned https Responses URL; no call is possible.")
            key = self._key or load_key(c.credential_ref)
            if key in packet.instructions or key in packet.text:
                raise BridgeError("credential_in_packet", "The packet contains the configured key; nothing was sent.")
            client = SolClient(key, transport=self._transport, url=self._url)
            self._budget()
            reserved = self.ledger.reserve(
                request_id=request_id, allocation=c.subscription_label, period=c.period_id, run=self.run_id, stage=c.phase,
                stage_cap=c.stage_cap, single_call=c.phase == "startup", packet_sha=packet.sha256, step=packet.step,
                input_bound=packet.input_bound, max_output=MAX_OUTPUT_TOKENS)
        except BridgeError as error:
            return failure(error)
        try:
            outcome = await client.ask(packet.instructions, packet.text)
        except BaseException:  # cancellation or a crash after dispatch is not proof of a zero bill
            self.ledger.finish(request_id, "held", detail="interrupted after dispatch; charge unknown")
            raise
        return self._conclude(request_id, packet, outcome, reserved)

    def _conclude(self, request_id, packet, outcome, reserved) -> dict:
        state = "released" if not outcome.dispatched else "settled" if outcome.input_tokens is not None else "held"
        quarantine = "upstream answered with a model other than the pinned Sol model" if outcome.kind == "model_mismatch" else None
        self.ledger.finish(request_id, state, input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens,
                           total_tokens=outcome.total_tokens, detail=outcome.kind, quarantine=quarantine)
        row = self.ledger.get(request_id)
        kind = outcome.kind if outcome.kind != "completed" or self._current_step() == packet.step else "stale_checkpoint"
        receipt = {"request_id": request_id, "kind": kind, "checkpoint": packet.step, "intent": packet.intent,
                   "model": outcome.model or None, "response_id": outcome.response_id or None, "http_status": outcome.http_status,
                   "detail": outcome.detail, "packet": packet.manifest | {"sha256": packet.sha256},
                   "usage": {"scope": "university_mcp", "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
                             "reasoning_tokens": outcome.reasoning_tokens, "cached_input_tokens": outcome.cached_input_tokens,
                             "charge": row["charge"], "inclusive_of_reasoning_and_cache": True, "state": state,
                             "reserved": reserved, "input_bound_tokens": packet.input_bound},
                   "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        try:
            self.local.mkdir(parents=True, exist_ok=True)
            if outcome.text:
                _atomic(self.local / f"{request_id}.txt", outcome.text)
            _atomic(self.local / f"{request_id}.json", json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            with (self.local / "usage.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"request_id": request_id, "checkpoint": packet.step, **receipt["usage"]}, sort_keys=True) + "\n")
            if kind == "completed":
                _atomic(self.local / "latest.json", json.dumps({"request_id": request_id, "step": packet.step}) + "\n")
            recorded = True
        except OSError:
            recorded = False
        payload = self._payload(receipt, outcome.text if kind in ("completed", "refused") else "", resumed=False)
        if not recorded:
            payload["local_record"] = "failed to write run files; the ledger still holds this call"
        from .telemetry import record
        payload["debrief_ledger"] = record(self.config, receipt, outcome.text if kind in ("completed", "refused") else "")
        return payload

    def _read_receipt(self, request_id):
        path = self.local / f"{request_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def _resume(self, row) -> dict:
        """A known request_id never causes HTTP: return what was recorded, at zero cost."""
        if row["run"] != self.run_id:
            raise BridgeError("request_id_reused", "This request_id belongs to another run; use a new unique ID.")
        receipt = self._read_receipt(row["request_id"])
        if receipt is None:
            raise BridgeError("call_in_flight" if row["state"] == "inflight" else "charge_held",
                              "This request was already dispatched and is never replayed. Its reservation stays counted.",
                              ledger_state=row["state"])
        if receipt["kind"] == "completed" and self._current_step() != receipt["checkpoint"]:
            receipt = dict(receipt, kind="stale_checkpoint")
        path = self.local / f"{row['request_id']}.txt"
        text = path.read_text(encoding="utf-8") if receipt["kind"] in ("completed", "refused") and path.is_file() else ""
        return self._payload(receipt, text, resumed=True)

    def _payload(self, receipt, text, resumed) -> dict:
        kind = receipt["kind"]
        payload = {"ok": kind == "completed", "kind": kind, "request_id": receipt["request_id"], "checkpoint": receipt["checkpoint"],
                   "model": receipt["model"], "usage": receipt["usage"], "detail": receipt["detail"],
                   "packet": {key: receipt["packet"][key] for key in ("sha256", "input_bytes", "input_bound_tokens")},
                   "provider_called": not resumed and receipt["usage"]["state"] != "released", "resumed": resumed,
                   "next": GUIDANCE.get(kind, HALT)}
        if text:
            payload["text"] = text
        try:
            payload["budget"] = self._budget()
        except BridgeError as error:
            payload["budget"] = {"problem": error.kind}
        return payload
