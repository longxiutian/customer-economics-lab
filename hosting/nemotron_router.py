"""Operator-owned background router and private worker client, using local IPC.

No listener/public port. CPU workers on this host enqueue through an ACL-protected
local SQLite queue; future remote CPU workers require an authenticated gateway.
No visible terminal windows: launch the daemon under the maintained windowless
Job Object supervisor. This module does not create schedules or allocate GPUs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from hosting.inference_router import FairRouter
from hosting.telemetry import Telemetry


def router(config):
    return FairRouter(config["queue_path"], Telemetry(config["telemetry_path"]), config["replicas"],
                      config_hash=config["profile_hash"], expires_at=config["expires_at"],
                      request_deadline=config.get("request_deadline", 150),
                      drain_margin=config.get("drain_margin", 15))


def serve(config):
    r = router(config)
    # Exclusive local filesystem lease; an abandoned lease requires operator recovery.
    lease = Path(config["queue_path"]).with_suffix(".owner.lock")
    lease.parent.mkdir(parents=True, exist_ok=True)
    with lease.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        r.recover_after_exclusive_restart()
        def invoke(spec, ticket):
            completed = subprocess.run([sys.executable, "-m", "hosting.router_provider"],
                input=json.dumps({"replica": spec, "ticket": ticket}).encode(), capture_output=True,
                timeout=r.request_deadline, cwd=Path(__file__).resolve().parents[1],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if completed.returncode:
                raise RuntimeError("Provider child did not return a settled completion")
            return json.loads(completed.stdout)
        with ThreadPoolExecutor(max_workers=sum(x["capacity"] for x in config["replicas"])) as pool:
            while time.time() < config["expires_at"]:
                for spec in config["replicas"]:
                    try:
                        health = json.loads(Path(spec["health_path"]).read_text(encoding="utf-8"))
                        # Endpoint must stay bound to the same owner/job/manifest attestation.
                        ready = health.get("ready") is True and health.get("job_id") == spec["job_id"] and health.get("base_url") == spec["base_url"] and not health.get("draining", True)
                        r.set_health(spec["id"], revision=health.get("revision"), config_hash=health.get("profile_hash"),
                                     manifest_hash=health.get("manifest_hash"), verified_at=health.get("last_checked_at", 0),
                                     expires_at=health.get("expires_at", 0), ready=ready)
                    except (OSError, ValueError):
                        r.health.pop(spec["id"], None)
                r.export_attempts()
                r.dispatch_available(pool, invoke)
                time.sleep(0.25)
    finally:
        lease.unlink(missing_ok=True)


def client(config, payload):
    context = payload.pop("telemetry_context")
    if context["session_id"] != config["session_id"]:
        raise ValueError("Worker and router session mismatch")
    r = router(config)
    r.submit(request_id=context["job_id"], run_id=context["run_id"], session_id=context["session_id"], payload=payload)
    until = min(time.time() + config.get("client_wait_seconds", 125), config["expires_at"])
    while time.time() < until:
        record = r.poll(context["job_id"], run_id=context["run_id"])
        if record["state"] in {"completed", "reconciled_completed"}:
            return record["result"]["response"]
        if record["state"] not in {"queued", "dispatched"}:
            raise RuntimeError("Interpretation requires operator reconciliation; no generation was repeated")
        time.sleep(0.25)
    raise TimeoutError("The original router request remains pollable; do not create a replacement")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--serve", action="store_true")
    args = p.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.serve:
        serve(config)
    else:
        print(json.dumps(client(config, json.load(sys.stdin)), ensure_ascii=False))


if __name__ == "__main__":
    main()
