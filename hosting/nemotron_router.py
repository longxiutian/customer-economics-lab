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
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid

from hosting.inference_router import FairRouter
from hosting.telemetry import Telemetry


def publish_progress(path, value):
    """Display-only publication: failures preserve the old timestamp, never work."""
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary.write_text(json.dumps(value),encoding='utf-8')
        temporary.replace(path)
    except OSError:
        pass
    finally:
        try:temporary.unlink(missing_ok=True)
        except OSError:pass


def router(config):
    return FairRouter(config["queue_path"], Telemetry(config["telemetry_path"]), config["replicas"],
                      config_hash=config["profile_hash"], expires_at=config["expires_at"],session_id=config['session_id'],
                      request_deadline=config.get("request_deadline", 150),
                      drain_margin=config.get("drain_margin", 15), max_queue=config.get('max_queue',128),
                      max_per_student=config.get('max_per_student',4), max_queue_wait=config.get('max_queue_wait',1800))


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
            pending=set()
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
                r.try_export()
                for future in list(pending):
                    if future.done():
                        try:future.result()
                        except Exception as exc:
                            print(json.dumps({'event':'router_settlement_requires_reconciliation','error_type':type(exc).__name__}),flush=True)
                        pending.remove(future)
                pending.update(r.dispatch_available(pool, invoke))
                if config.get('status_path'):
                    ready=[spec for spec in config['replicas'] if (h:=r.health.get(spec['id'],{})).get('ready')
                           and h.get('revision')==spec['revision'] and h.get('manifest_hash')==spec['manifest_hash']
                           and h.get('config_hash')==r.config_hash and 0<=time.time()-h.get('verified_at',0)<=r.health_ttl
                           and h.get('expires_at',0)>time.time()+r.request_deadline+r.drain_margin]
                    publish_progress(config['status_path'],{'ready':len(ready)>=config.get('minimum_ready_replicas',1),
                        'ready_replicas':len(ready),'admission_capacity':sum(x['capacity'] for x in ready),
                        'last_checked_at':time.time(),'expires_at':config['expires_at'],'telemetry_export_error':r.last_export_error})
                time.sleep(0.25)
    finally:
        r.expire_queued()
        lease.unlink(missing_ok=True)


def client(config, payload):
    context = payload.pop("telemetry_context")
    if context["session_id"] != config["session_id"]:
        raise ValueError("Worker and router session mismatch")
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',context['job_id']):
        raise ValueError('Invalid trusted broker job ID')
    payload['_deadline'] = min(context.get('deadline',config['expires_at']),config['expires_at'])
    r = router(config)
    r.submit(request_id=context["job_id"], run_id=context["run_id"], session_id=context["session_id"], payload=payload)
    until = min(time.time() + config.get("client_wait_seconds", 1800), payload['_deadline'])
    progress_path=Path(config['client_progress_root'])/(context['job_id']+'.json') if config.get('client_progress_root') else None
    last_progress=0
    while time.time() < until:
        record = r.poll(context["job_id"], run_id=context["run_id"])
        if progress_path and time.time()-last_progress>=2:
            publish_progress(progress_path,{**record['progress'],'source':'router'})
            last_progress=time.time()
        if record["state"] in {"completed", "reconciled_completed"}:
            return record["result"]["response"]
        if record["state"] not in {"queued", "dispatched"}:
            raise RuntimeError("Interpretation requires operator reconciliation; no generation was repeated")
        time.sleep(1)
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
