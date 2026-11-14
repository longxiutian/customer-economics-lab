"""Copy bridge receipts into the lab's existing local debrief ledger, idempotently."""
from __future__ import annotations

import importlib
import calendar
import sys
import time
from pathlib import Path


def record(config, receipt, text):
    # Preparation initializes this explicitly with the actual harness name.
    if not (config.run_dir / "usage/session.json").is_file():
        return "not_initialized"
    root = str(config.source_root)
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        module = importlib.import_module("cohort_lab.debrief")
        if not Path(module.__file__).resolve().is_relative_to(config.source_root):
            return "source_conflict"
        request_id, usage = receipt["request_id"], receipt["usage"]
        happened_at = calendar.timegm(time.strptime(receipt["completed_at"], "%Y-%m-%dT%H:%M:%SZ"))
        scope = "debrief" if receipt["intent"] == "debrief" else "university_mcp"
        module.record(config.run_dir, {
            "event_id": f"sol-usage-{request_id}", "kind": "usage",
            "provider": "UNC APIM", "model": receipt["model"] or "unreported",
            "meter_scope": scope, "stream_id": "unc-sol-bridge", "mode": "call",
            "source": f"sol_bridge/{request_id}.json", "semantics": "openai_inclusive",
            "usage": {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]},
            "happened_at": happened_at,
        })
        if text:
            module.record(config.run_dir, {
                "event_id": f"sol-reply-{request_id}", "kind": "text",
                "role": "tool", "scope": "debrief" if receipt["intent"] == "debrief" else "lab",
                "text": text, "happened_at": happened_at,
            })
        return "recorded"
    except Exception:
        # Settlement is authoritative even if a separate debrief write failed.
        return "failed; keep the bridge receipt for reconciliation"
    finally:
        if added:
            sys.path.remove(root)
