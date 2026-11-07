"""Bounded outbound worker. Run with the frozen lab Python, never in BlueChip's sandbox."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cohort_lab.hosted import HostedLesson, release_manifest, write_json


class Broker:
    def __init__(self, config):
        self.config = config

    def request(self, path, value=None, *, method="POST", data=None, headers=None):
        config = self.config
        h = {"Authorization": "Bearer " + config["worker_key"], "X-Worker-Id": config["worker_id"],
             "User-Agent": "StudioNorth-LabWorker/1"}
        if config.get("sites_service_token"):
            h["OAI-Sites-Authorization"] = "Bearer " + config["sites_service_token"]
        if data is None:
            data = json.dumps(value or {}).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        request = Request(config["broker_url"].rstrip("/") + path, data=data, headers=h, method=method)
        # Retrying delivery of the same job is safe; executing it again is not.
        for attempt in range(4):
            try:
                with urlopen(request, timeout=25) as response:
                    return json.load(response)
            except HTTPError as exc:
                if exc.code < 500 or attempt == 3:
                    raise RuntimeError(f"Broker HTTP {exc.code}: {exc.read(1500).decode(errors='replace')}") from None
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise
            time.sleep(min(2 ** attempt, 4))


def interpreter(config):
    """A separate maintained interpreter process owns private model credentials."""
    command = config.get("interpreter_command")
    if not command:
        return None
    if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
        raise ValueError("interpreter_command must be an operator-configured argument array")

    def interpret(packet, question):
        evidence = {k: v for k, v in packet.items() if k not in {"interpretation"}}
        evidence["artifacts"] = [{k: v for k, v in a.items() if k not in {"local_path", "url"}}
                                 for a in evidence.get("artifacts", [])]
        prompt = {"question": question, "evidence": evidence}
        encoded = json.dumps(prompt, ensure_ascii=False).encode()
        p = subprocess.run(command, input=encoded, capture_output=True, timeout=150,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if p.returncode:
            write_json(Path(config["runtime"]) / "interpreter-errors" / (str(time.time_ns()) + ".json"),
                       {"returncode": p.returncode, "stderr": p.stderr.decode("utf-8", errors="replace")[-4000:],
                        "evidence_sha256": hashlib.sha256(encoded).hexdigest()})
            raise RuntimeError("Nemotron interpreter did not complete: " + p.stderr.decode("utf-8", errors="replace")[-1500:])
        result = json.loads(p.stdout)
        if result.get("status") != "completed" or not result.get("model") or not result.get("text"):
            raise RuntimeError("Missing verified model response")
        result["evidence_sha256"] = hashlib.sha256(encoded).hexdigest()
        return result
    return interpret


def execute_one(config, job_path, result_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    lesson = HostedLesson(Path(config["runtime"]), interpreter=interpreter(config))
    try:
        result = lesson.execute(job)
        write_json(Path(result_path), {"result": result})
    except Exception as exc:
        write_json(Path(result_path), {"error": f"{type(exc).__name__}: {exc}"})
        return 1
    return 0


def run(config, config_path):
    broker = Broker(config)
    runtime = Path(config["runtime"])
    runtime.mkdir(parents=True, exist_ok=True)
    manifest = release_manifest()
    if manifest["release_hash"] != config["release_hash"]:
        raise RuntimeError("Pinned release changed; worker was not started")
    expiry = float(config["expires_at"])
    if expiry <= time.time() or expiry - time.time() > 5 * 3600 + 120:
        raise RuntimeError("This rehearsal needs a future expiry no more than five hours away")
    live = {"job_id": None}
    stopping = threading.Event()

    def heartbeat():
        while not stopping.is_set() and time.time() < expiry:
            status = {"cpu": "ready", "nemotron": "configured_unverified" if config.get("interpreter_command") else "unavailable"}
            model_status = Path(config.get("model_status_path", "__missing__"))
            if model_status.is_file():
                status["nemotron"] = json.loads(model_status.read_text(encoding="utf-8"))
            try:
                broker.request("/api/worker/heartbeat", {"release_hash": manifest["release_hash"], "expires_at": expiry,
                               "job_id": live["job_id"], "status": status})
                write_json(runtime / "worker-health.json", {"heartbeat": time.time(), "expires_at": expiry,
                           "job_id": live["job_id"], "status": status, "release_hash": manifest["release_hash"]})
            except Exception as exc:
                print(json.dumps({"event": "heartbeat_failed", "type": type(exc).__name__}), flush=True)
            stopping.wait(15)

    # Register synchronously before claiming jobs.
    broker.request("/api/worker/heartbeat", {"release_hash": manifest["release_hash"], "expires_at": expiry,
                   "status": {"cpu": "ready", "nemotron": "configured_unverified" if config.get("interpreter_command") else "unavailable"}})
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        while time.time() < expiry:
            try:
                job = broker.request("/api/worker/claim").get("job")
            except Exception as exc:
                print(json.dumps({"event": "claim_failed", "type": type(exc).__name__}), flush=True)
                stopping.wait(5)
                continue
            if not job:
                stopping.wait(2)
                continue
            live["job_id"] = job["id"]
            spool = runtime / "spool" / job["id"]
            spool.mkdir(parents=True, exist_ok=True)
            job_file, result_file = spool / "job.json", spool / "result.json"
            write_json(job_file, job)
            print(json.dumps({"event": "job_started", "job_id": job["id"], "checkpoint": job["checkpoint"]}), flush=True)
            command = [sys.executable, str(Path(__file__).resolve()), "--config", str(config_path),
                       "--execute", str(job_file), "--result", str(result_file)]
            with (spool / "execution.log").open("wb") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    process.wait(timeout=max(1, min(3600, expiry-time.time())))
                except subprocess.TimeoutExpired:
                    # Windows deployment places the complete tree in a kill-on-close Job Object.
                    # Exit the outer process so that supervisor teardown also kills descendants.
                    write_json(spool / "interrupted.json", {"reason": "execution_or_session_deadline", "job_id": job["id"]})
                    return 2
            if not result_file.is_file():
                body = {"error": "Worker exited without a durable result; operator review is required"}
            else:
                body = json.loads(result_file.read_text(encoding="utf-8"))
            try:
                if "result" in body:
                    for artifact in body["result"]["packet"].get("artifacts", []):
                        if artifact["size"] > 8*1024*1024:
                            artifact.update(available=False, download_note="Exceeds browser artifact limit; preview retained")
                            artifact.pop("local_path", None)
                            continue
                        path = Path(artifact.pop("local_path"))
                        data = path.read_bytes()
                        if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
                            raise RuntimeError("Artifact changed between computation and upload")
                        broker.request("/api/worker/artifact?job_id=" + job["id"], method="PUT", data=data,
                            headers={"Content-Type": artifact["mime"], "X-Artifact-Id": artifact["artifact_id"],
                                     "X-Artifact-Name": quote(artifact["name"], safe=""), "X-Artifact-SHA256": artifact["sha256"]})
                broker.request("/api/worker/finish?job_id=" + job["id"], body)
                write_json(spool / "delivered.json", {"job_id": job["id"], "delivered_at": time.time(), "success": "result" in body})
                print(json.dumps({"event": "job_delivered", "job_id": job["id"], "success": "result" in body}), flush=True)
            except Exception as exc:
                # Preserve the original result for operator redelivery. Never reexecute on a transport error.
                write_json(spool / "delivery-failed.json", {"job_id": job["id"], "error_type": type(exc).__name__})
                print(json.dumps({"event": "delivery_failed", "job_id": job["id"], "type": type(exc).__name__}), flush=True)
                return 3
            live["job_id"] = None
    finally:
        stopping.set()
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--execute", type=Path)
    p.add_argument("--result", type=Path)
    args = p.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    return execute_one(config, args.execute, args.result) if args.execute else run(config, args.config)

if __name__ == "__main__":
    raise SystemExit(main())
