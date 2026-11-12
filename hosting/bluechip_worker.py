"""Bounded outbound worker. Run with the frozen lab Python, never in BlueChip's sandbox."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import threading
import traceback
import uuid
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
        if data is None and method not in {'GET','HEAD'}:
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


def deliver_result(broker, job, body):
    """Idempotent delivery only; this function never executes a lesson or model."""
    settled=broker.request('/api/worker/job_status?job_id='+job['id'],method='GET')
    if settled['status']=='completed' or (settled['status']=='failed' and 'error' in body):
        if settled['status']=='completed':
            observe_files(broker, job)
        return
    body=json.loads(json.dumps(body))
    if 'result' in body:
        for artifact in body['result']['packet'].get('artifacts',[]):
            if 'local_path' not in artifact:
                continue
            if artifact['size']>8*1024*1024:
                artifact.update(available=False,download_note='Exceeds browser artifact limit; preview retained')
                artifact.pop('local_path',None)
                continue
            path=Path(artifact.pop('local_path'));data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=artifact['sha256']:
                raise RuntimeError('Artifact changed between computation and upload')
            broker.request('/api/worker/artifact?job_id='+job['id'],method='PUT',data=data,
                headers={'Content-Type':artifact['mime'],'X-Artifact-Id':artifact['artifact_id'],
                         'X-Artifact-Name':quote(artifact['name'],safe=''),'X-Artifact-SHA256':artifact['sha256']})
    broker.request('/api/worker/finish?job_id='+job['id'],body)
    if 'result' in body:
        observe_files(broker, job)


def observe_files(broker, job):
    """File metadata is separate from calculation receipts and cannot fail a fit."""
    if broker.config.get('lane') == 'debrief' or broker.config.get('file_map_paths_disclosable') is not True:
        return
    try:
        from hosting.file_manifest import build_manifest
        config = broker.config
        observation = build_manifest(ROOT, Path(config['runtime'])/'workspaces'/job['run_id'],
                                     session_id=config['session_id'], store_id=config['store_id'], paths_disclosable=True)
        broker.request('/api/worker/manifest', observation, method='PUT')
    except Exception as exc:
        print(json.dumps({'event':'file_map_pending','run_id':job['run_id'],'error_type':type(exc).__name__}),flush=True)


def redeliver_until(broker, job, result_file, spool, *, deadline, live, stopping):
    delay=1
    while time.time()<deadline and not stopping.is_set():
        try:
            body=json.loads(result_file.read_text(encoding='utf-8'))
            deliver_result(broker,job,body)
            write_json(spool/'delivered.json',{'job_id':job['id'],'delivered_at':time.time(),'success':'result' in body})
            live['cpu']='ready'
            return True
        except Exception as exc:
            live['cpu']='delivery_pending'
            try:write_json(spool/'delivery-failed.json',{'job_id':job['id'],'error_type':type(exc).__name__,'at':time.time()})
            except OSError:pass
            print(json.dumps({'event':'delivery_retry','job_id':job['id'],'type':type(exc).__name__}),flush=True)
            stopping.wait(min(delay,max(0,deadline-time.time())))
            delay=min(15,delay*2)
    return False


def interpreter(config, *, job=None):
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
        if config.get("telemetry") and job:
            prompt["telemetry_context"] = {"job_id": job["id"], "run_id": job["run_id"],
                                           "session_id": config["telemetry"]["session_id"],
                                           "deadline":job.get('deadline',config['expires_at'])}
        encoded = json.dumps(prompt, ensure_ascii=False).encode()
        p = subprocess.run(command, input=encoded, capture_output=True,
                           timeout=max(1,min(config.get('interpreter_wait_seconds',1860),job.get('deadline',config['expires_at'])-time.time()-10)) if job else 150,
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
    def progress(phase):
        write_json(Path(config.get('progress_root',Path(config['runtime'])/'progress'))/(job['id']+'.json'),
                   {'queue_kind':phase,'state':'running','as_of':time.time(),'source':'worker'})
    from hosting.hosted_debrief import create as create_debrief
    lesson = HostedLesson(Path(config["runtime"]), interpreter=interpreter(config, job=job),progress=progress,
                          automatic_test_until=min(float(config.get('automatic_test_until', 0)), float(config['expires_at'])),
                          debriefer=lambda output,receipts,request:create_debrief(config,output,receipts,request))
    try:
        if job['payload']['action']=='debrief' and job.get('source_packet'):
            from hosting.hosted_debrief import execute_assigned
            result=execute_assigned(config,job)
        else:
            result = lesson.execute(job)
            if result['packet'].get('validation',{}).get('report_complete') and config.get('telemetry'):
                from hosting.hosted_debrief import prepare
                base,output,receipts=lesson.locations(job['run_id'])
                result['packet']['debrief_input']=prepare(config,output,receipts,job)
                receipt=receipts/(job['id']+'.json')
                saved=json.loads(receipt.read_text(encoding='utf-8'));saved['result']=result;write_json(receipt,saved)
        write_json(Path(result_path), {"result": result})
    except Exception as exc:
        error_id=uuid.uuid4().hex
        traceback.print_exc()  # Instructor-owned execution log only.
        message='The query was rejected. Check the released table and column names, then retry at this checkpoint.' if job['payload']['action']=='query' else 'This operation needs an instructor check. Saved work has been preserved.'
        write_json(Path(result_path), {"error": message+' Reference '+error_id, 'error_type':type(exc).__name__})
        return 1
    finally:
        if config.get("telemetry"):
            # Receipts are durable before telemetry aggregation. A missing event can
            # be backfilled without repeating the student's analysis or generation.
            from hosting.telemetry import Telemetry
            telemetry = config["telemetry"]
            try:
                receipt = Path(config["runtime"]) / "workspaces" / job["run_id"] / "receipts" / (job["id"] + ".json")
                if receipt.is_file() and job['payload']['action']!='debrief':
                    Telemetry(telemetry["path"]).ingest_receipt(json.loads(receipt.read_text(encoding="utf-8")), session_id=telemetry["session_id"])
                health = {"status": "recorded", "job_id": job["id"], "checked_at": time.time()}
            except Exception as exc:
                health = {"status": "backfill_required", "job_id": job["id"], "error_type": type(exc).__name__, "checked_at": time.time()}
            try:write_json(Path(config["runtime"]) / (config['worker_id']+'-telemetry-health.json'), health)
            except OSError:pass
    return 0


def run(config, config_path):
    broker = Broker(config)
    runtime = Path(config["runtime"])
    runtime.mkdir(parents=True, exist_ok=True)
    session_id=config.get('session_id')
    if not session_id or session_id!=config.get('telemetry',{}).get('session_id') or not config['worker_id'].startswith(session_id+'-'):
        raise RuntimeError('Worker, telemetry and worker ID must share the explicit session identity')
    saved_store=json.loads((runtime/'store.json').read_text(encoding='utf-8'))
    if saved_store.get('store_id')!=config.get('store_id') or saved_store.get('session_id')!=session_id:
        raise RuntimeError('The worker runtime does not match its registered workspace store')
    manifest = release_manifest()
    if manifest["release_hash"] != config["release_hash"]:
        raise RuntimeError("Pinned release changed; worker was not started")
    expiry = float(config["expires_at"])
    if expiry <= time.time() or expiry - time.time() > 5 * 3600 + 120:
        raise RuntimeError("This rehearsal needs a future expiry no more than five hours away")
    live = {"job_id": None}
    process = None
    stopping = threading.Event()

    def heartbeat():
        while not stopping.is_set() and time.time() < expiry:
            try:
                status = {"cpu": live.get('cpu','ready'), "lane":config.get('lane','interactive'), "nemotron": "configured_unverified" if config.get("interpreter_command") else "unavailable"}
                model_status = Path(config.get("model_status_path", "__missing__"))
                if model_status.is_file():
                    try:
                        raw_status=json.loads(model_status.read_text(encoding="utf-8"))
                        status["nemotron"]={k:raw_status[k] for k in ('ready','status','model','revision','expires_at','verified_at','last_checked_at','ready_replicas','admission_capacity') if k in raw_status}
                    except (OSError,ValueError):status['nemotron']={'ready':False,'status':'health_update_unavailable'}
                progress_path=Path(config.get('progress_root',runtime/'progress'))/(str(live['job_id'])+'.json')
                try:progress=json.loads(progress_path.read_text(encoding='utf-8')) if live['job_id'] and progress_path.is_file() else None
                except (OSError,ValueError):progress=None
                if progress and progress.get('source')=='worker':
                    progress['as_of']=time.time()
                broker.request("/api/worker/heartbeat", {"release_hash": manifest["release_hash"], "expires_at": expiry,
                               'session_id':session_id,'store_id':config['store_id'],
                               "job_id": live["job_id"], "status": status,'progress':progress})
                write_json(runtime / (config['worker_id']+'-health.json'), {"heartbeat": time.time(), "expires_at": expiry,
                           "job_id": live["job_id"], "status": status, "release_hash": manifest["release_hash"]})
            except Exception as exc:
                print(json.dumps({"event": "heartbeat_failed", "type": type(exc).__name__}), flush=True)
            stopping.wait(3 if live['job_id'] else 15)

    # Register synchronously before claiming jobs.
    broker.request("/api/worker/heartbeat", {"release_hash": manifest["release_hash"], "expires_at": expiry,
                   'session_id':session_id,'store_id':config['store_id'],
                   "status": {"cpu": "ready", "lane":config.get('lane','interactive'), "nemotron": "configured_unverified" if config.get("interpreter_command") else "unavailable"}})
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        # Recover only a durable result from this worker's spool. An unfinished
        # execution has no permission to restart, even after its lease expires.
        for job_file in sorted((runtime/'spool').glob('*/job.json')):
            spool=job_file.parent
            if (spool/'delivered.json').is_file():continue
            job=json.loads(job_file.read_text(encoding='utf-8'))
            if job.get('worker')!=config['worker_id'] or job.get('release_hash')!=manifest['release_hash']:continue
            live['job_id']=job['id'];result_file=spool/'result.json'
            if not result_file.is_file():
                receipt=runtime/'workspaces'/job['run_id']/'receipts'/(job['id']+'.json')
                saved=json.loads(receipt.read_text(encoding='utf-8')) if receipt.is_file() else {}
                if saved.get('status')!='completed' or 'result' not in saved:
                    live['cpu']='recovery_required'
                    return 4
                write_json(result_file,{'result':saved['result']})
            if not redeliver_until(broker,job,result_file,spool,deadline=expiry,live=live,stopping=stopping):return 3
            live['job_id']=None
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
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                           start_new_session=os.name!='nt')
                try:
                    process.wait(timeout=max(1, min(3600, expiry-time.time(),job.get('deadline',expiry)-time.time())))
                except subprocess.TimeoutExpired:
                    # Windows deployment places the complete tree in a kill-on-close Job Object.
                    # Exit the outer process so that supervisor teardown also kills descendants.
                    write_json(spool / "interrupted.json", {"reason": "execution_or_session_deadline", "job_id": job["id"]})
                    return 2
            if not result_file.is_file():
                write_json(result_file,{"error": "Worker exited without a durable result; operator review is required"})
            if not redeliver_until(broker,job,result_file,spool,deadline=expiry,live=live,stopping=stopping):return 3
            live["job_id"] = None
    finally:
        stopping.set()
        if os.name!='nt' and process and process.poll() is None:
            # Own only the execution child's new process group, including TeX,
            # browser renderers and interpreter children. Slurm is the outer owner.
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
    return 0


def main():
    if os.name!='nt':
        def stop(*_):raise SystemExit(143)
        signal.signal(signal.SIGTERM,stop)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--execute", type=Path)
    p.add_argument("--result", type=Path)
    args = p.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    return execute_one(config, args.execute, args.result) if args.execute else run(config, args.config)

if __name__ == "__main__":
    raise SystemExit(main())
