"""Slurm-owned CPU workers and one node-local Nemotron router.

This supervisor never allocates resources, restarts a worker, or replays work.
Only the router inherits model credentials. SQLite databases stay node local;
durable workspaces, verified backups, and exit receipts stay in the owned store.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{8,80}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
LOCAL_FILESYSTEMS = {"ext2", "ext3", "ext4", "xfs", "tmpfs", "btrfs"}


def write_json(path: Path, value, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            # Publish a complete file without an overwrite or a partial-read race.
            os.link(temporary, path)
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def bind_store(runtime: Path, session_id: str, store_id: str):
    expected = {"session_id": session_id, "store_id": store_id}
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "store.json"
    try:
        write_json(path, expected, exclusive=True)
    except FileExistsError:
        pass
    if json.loads(path.read_text(encoding="utf-8")) != expected:
        raise ValueError("Runtime store identity mismatch; existing store was preserved")


def cpu_list(value, count):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(,\d+)*", value):
        raise ValueError("CPU assignment must be explicit integer IDs")
    result = tuple(int(x) for x in value.split(","))
    if len(result) != count or len(set(result)) != count:
        raise ValueError("CPU assignment has missing or duplicate slots")
    return result


def worker_environment(environment):
    result = {k: v for k, v in environment.items()
              if not (k.startswith("STUDIO_NORTH_GPU") and k.endswith("_TOKEN"))
              and k not in {"BLUECHIP_METERED_SERVICE_TOKEN", "STUDIO_NORTH_METERED_URL"}}
    result.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                  NUMEXPR_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1", BLIS_NUM_THREADS="1",
                  TF_NUM_INTRAOP_THREADS="1", TF_NUM_INTEROP_THREADS="1",
                  JAX_PLATFORMS="cpu", JAX_ENABLE_X64="true", CUDA_VISIBLE_DEVICES="-1",
                  PYTHONUNBUFFERED="1")
    return result


def finite_deadline(value, now):
    value = float(value)
    if not math.isfinite(value) or not now + 180 < value <= now + 5 * 3600 + 120:
        raise ValueError("Rehearsal deadline must be between three minutes and five hours away")
    return value


@dataclass(frozen=True)
class Plan:
    config: dict
    jobtmp: Path
    runtime: Path
    router_path: Path
    router: dict
    analysis_cpus: tuple
    helper_cpus: tuple
    deadline: float
    parent_job_id: str


def validate(config, environment, router, *, now, affinity, topology):
    for key in ("session_id", "store_id"):
        if not isinstance(config.get(key), str) or not IDENTIFIER.fullmatch(config[key]):
            raise ValueError("Invalid explicit session/store identity")
    for key in ("release_hash", "source_release_sha256"):
        if not isinstance(config.get(key), str) or not HASH.fullmatch(config[key]):
            raise ValueError("Missing frozen release hash")
    if config["source_release_sha256"] != environment.get("STUDIO_NORTH_RELEASE_SHA256"):
        raise ValueError("Slurm source-release binding mismatch")
    for key, field in (("LAB_SESSION_ID", "session_id"), ("LAB_ANALYSIS_STORE_ID", "store_id")):
        if key in environment and environment[key] != config[field]:
            raise ValueError("Broker and worker identity disagree")
    if not isinstance(config.get("worker_key"), str) or not config["worker_key"]:
        raise ValueError("Missing restricted broker worker credential")
    if not isinstance(config.get("broker_url"), str) or not config["broker_url"].startswith("https://"):
        raise ValueError("Broker URL must use HTTPS")
    counts = (config.get("analysis_workers", 21), config.get("interactive_workers", 8))
    if any(type(n) is not int for n in counts) or not 1 <= counts[0] <= 45 or not 1 <= counts[1] <= 8:
        raise ValueError("Worker counts exceed the reviewed pool bounds")
    # One distinct physical core per analysis worker; learner count is independent.
    analysis = cpu_list(environment.get("STUDIO_NORTH_ANALYSIS_CPUS"), counts[0])
    helpers = cpu_list(environment.get("STUDIO_NORTH_HELPER_CPUS"), 3)
    all_cpus = analysis + helpers
    required_cores = counts[0] + len(helpers)
    if len(set(all_cpus)) != required_cores or not set(all_cpus) <= set(affinity):
        raise ValueError("CPU slots overlap or escape Slurm affinity")
    if any(cpu not in topology for cpu in all_cpus) or len({topology[cpu] for cpu in all_cpus}) != required_cores:
        raise ValueError(f"The {required_cores} slots must be distinct physical cores")
    parent = environment.get("STUDIO_NORTH_PARENT_JOB_ID", "")
    if not re.fullmatch(r"[1-9]\d*", parent):
        raise ValueError("Missing Slurm parent identity")
    jobtmp = PurePosixPath(environment.get("STUDIO_NORTH_JOB_RUNTIME", ""))
    runtime = PurePosixPath(config.get("runtime", ""))
    if not jobtmp.is_absolute() or not runtime.is_absolute() or jobtmp == runtime:
        raise ValueError("Explicit separate node-local and durable runtimes are required")
    if ".." in jobtmp.parts or ".." in runtime.parts or (sys.platform == "linux" and
            (Path(jobtmp).resolve() != jobtmp or Path(runtime).resolve() != runtime)):
        raise ValueError("Runtime paths must be canonical without symlink aliases")
    if not str(runtime).startswith("/hickory/"):
        raise ValueError("Durable worker outputs must be on Hickory")
    supervisor_end = finite_deadline(environment.get("STUDIO_NORTH_JOB_END"), now)
    deadline = finite_deadline(router.get("expires_at"), now)
    if deadline > supervisor_end - 30:
        raise ValueError("Work expiry must leave at least 30 seconds for owned cleanup")
    if router.get("session_id") != config["session_id"]:
        raise ValueError("Router session mismatch")
    for key, name in (("queue_path", "router.sqlite"), ("telemetry_path", "telemetry.sqlite"),
                      ("client_progress_root", "progress"), ("status_path", "model-status.json")):
        if router.get(key) != str(jobtmp / name):
            raise ValueError("Router IPC paths must match the node-local worker paths")
    replicas = router.get("replicas", [])
    if len(replicas) != 4 or any(r.get("capacity") != 2 for r in replicas):
        raise ValueError("Expected four reviewed replicas with two admissions each")
    if router.get("minimum_ready_replicas", 1) != 4:
        raise ValueError("All four replicas are required for this rehearsal")
    return Plan(config, Path(jobtmp), Path(runtime), Path(jobtmp / "router-runtime.json"), router,
                analysis, helpers, deadline, parent)


def worker_config(plan, lane, index):
    cfg = plan.config
    return {key: cfg[key] for key in ("broker_url", "worker_key", "session_id", "store_id", "release_hash")} | {
        "sites_service_token": cfg.get("sites_service_token", ""), "runtime": str(plan.runtime),
        "worker_id": f"{cfg['session_id']}-{lane}-{index:03d}", "lane": lane,
        "expires_at": plan.deadline, "debrief_enabled": False,
        "telemetry": {"path": str(plan.jobtmp / "telemetry.sqlite"), "session_id": cfg["session_id"]},
        "progress_root": str(plan.jobtmp / "progress"),
        "model_status_path": str(plan.jobtmp / "model-status.json"),
        "interpreter_command": [sys.executable, "-m", "hosting.nemotron_router", "--config", str(plan.router_path)]}


def proc_snapshot():
    """Read process identities without relying on reusable PIDs alone."""
    result = {}
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            raw = (item / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            result[int(item.name)] = {"ppid": int(fields[1]), "group": int(fields[2]),
                "state": fields[0], "start": int(fields[19]),
                "rss": int(fields[21]) * os.sysconf("SC_PAGE_SIZE")}
        except (OSError, ValueError, IndexError):
            continue
    return result


def descendants(snapshot, roots):
    found = set(roots)
    while True:
        newer = found | {pid for pid, row in snapshot.items() if row["ppid"] in found}
        if newer == found:
            return found
        found = newer


class ProcessOwner:
    def __init__(self, logs: Path):
        self.logs = logs
        logs.mkdir(parents=True, exist_ok=True)
        self.children = []
        self.known = {}
        self.slots = {}

    def adopt_orphans(self):
        # Descendants that create their own sessions still become OUR children
        # after their parent exits. This never adopts another allocation's work.
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot establish child-subreaper ownership")

    def spawn(self, command, *, name, cpus, environment):
        handle = (self.logs / (name + ".log")).open("xb")
        try:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=handle, stderr=handle,
                env=dict(environment, STUDIO_NORTH_POOL_SLOT=name), cwd=ROOT, start_new_session=True,
                preexec_fn=lambda: os.sched_setaffinity(0, set(cpus)))
        finally:
            handle.close()
        record = {"process": child, "name": name, "cpus": tuple(cpus), "started_at": time.time(), "peak_rss_bytes": 0}
        record["process_start"] = proc_snapshot().get(child.pid, {}).get("start")
        self.children.append(record)
        return record

    def observe(self):
        snapshot = proc_snapshot()
        owned = descendants(snapshot, {os.getpid()}) - {os.getpid()}
        for pid in owned:
            if self.known.get(pid) != snapshot[pid]["start"]:
                self.slots.pop(pid, None)
            self.known[pid] = snapshot[pid]["start"]
            if pid not in self.slots:
                # Read only OUR descendants' inherited tag; never serialize their
                # environment (which may contain a router credential).
                with contextlib.suppress(OSError):
                    for field in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
                        if field.startswith(b"STUDIO_NORTH_POOL_SLOT="):
                            self.slots[pid] = field.split(b"=", 1)[1].decode("utf-8", "strict")
                            break
        for record in self.children:
            pid = record["process"].pid
            root = {pid} if snapshot.get(pid, {}).get("start") == record["process_start"] else set()
            members = descendants(snapshot, root) | {pid for pid in owned if self.slots.get(pid) == record["name"]}
            for pid in members & owned:
                self.slots[pid] = record["name"]
            rss = sum(snapshot[p]["rss"] for p in members if p in snapshot)
            record["peak_rss_bytes"] = max(record["peak_rss_bytes"], rss)
            record["current_rss_bytes"] = rss
        return snapshot

    def _signal_owned(self, signum, names=None):
        snapshot = self.observe()
        for pid, start in list(self.known.items()):
            if (pid in snapshot and snapshot[pid]["start"] == start and snapshot[pid]["state"] != "Z"
                    and (names is None or self.slots.get(pid) in names)):
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signum)

    def stop_slots(self, records, grace=.5):
        """Terminate only an exited slot's attributable descendants, not siblings."""
        self._stop(records, {r["name"] for r in records}, grace)

    def stop(self, grace=8):
        self._stop(self.children, None, grace)

    def _stop(self, records, names, grace):
        self._signal_owned(signal.SIGTERM, names)
        until = time.monotonic() + grace
        while time.monotonic() < until:
            for record in records:
                record["process"].poll()
            snap = self.observe()
            live = [pid for pid, start in self.known.items() if pid in snap and snap[pid]["start"] == start and snap[pid]["state"] != "Z"
                    and (names is None or self.slots.get(pid) in names)]
            if not live:
                break
            time.sleep(0.1)
        kill_until = time.monotonic() + 2
        # Re-scan to catch an owned process that forked during the final signal.
        while time.monotonic() < kill_until:
            self._signal_owned(signal.SIGKILL, names)
            for record in records:
                record["process"].poll()
            snap = self.observe()
            if not any(pid in snap and snap[pid]["start"] == start and snap[pid]["state"] != "Z"
                       and (names is None or self.slots.get(pid) in names)
                       for pid, start in self.known.items()):
                break
            time.sleep(0.05)
        for record in records:
            with contextlib.suppress(subprocess.TimeoutExpired):
                record["process"].wait(timeout=max(.01, kill_until-time.monotonic()))
        if names is not None:
            return
        # Reap adopted grandchildren after direct Popen children were waited.
        until = time.monotonic() + 1
        while time.monotonic() < until:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not pid:
                time.sleep(0.02)


def worker_inventory(owner, workers, receipts, identity):
    """A dead worker reduces capacity; it does not kill or restart other slots."""
    failed = [r for r in workers if r["process"].poll() is not None]
    unsettled = [r for r in failed if not r.get("exit_recorded")]
    if unsettled:
        owner.stop_slots(unsettled)
    for record in unsettled:
        try:
            write_json(receipts / (record["name"] + "-exit.json"), identity | {
                "name": record["name"], "pid": record["process"].pid, "returncode": record["process"].poll(),
                "started_at": record["started_at"], "ended_at": time.time(), "cpus": record["cpus"],
                "peak_observed_tree_rss_bytes": record["peak_rss_bytes"], "reason": "worker_slot_exited",
                "restarted": False, "other_workers_stopped": False}, exclusive=True)
            record["exit_recorded"] = True
            record.pop("exit_receipt_error", None)
        except OSError as exc:
            record["exit_receipt_error"] = type(exc).__name__
    alive = [r for r in workers if r["process"].poll() is None]
    return alive, {"degraded": bool(failed), "failed_slots": [r["name"] for r in failed],
                   "exit_receipts_pending": [r["name"] for r in failed if not r.get("exit_recorded")],
                   "remaining_analysis_slots": sum(r["lane"] == "analysis" for r in alive),
                   "remaining_interactive_slots": sum(r["lane"] == "interactive" for r in alive)}


def backup_sqlite(source, destination, *, timeout=4):
    """Use SQLite's consistent backup API; never copy a live database or WAL."""
    if not source.is_file():
        return None
    temporary = source.with_name(source.name + ".backup-" + uuid.uuid4().hex)
    until = time.monotonic() + timeout
    def progress(*_):
        if time.monotonic() > until:
            raise TimeoutError("Bounded SQLite backup did not settle")
    try:
        with contextlib.closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1)) as src:
            with contextlib.closing(sqlite3.connect(temporary)) as dest:
                src.backup(dest, pages=128, progress=progress, sleep=0.05)
                if dest.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("SQLite backup integrity check failed")
        data = temporary.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        digest = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Durable backup checksum mismatch")
        return {"path": str(destination), "sha256": digest, "bytes": len(data)}
    finally:
        temporary.unlink(missing_ok=True)


def topology_for(cpus):
    result = {}
    for cpu in cpus:
        root = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        result[cpu] = (int((root / "physical_package_id").read_text()), int((root / "core_id").read_text()))
    return result


def check_local_runtime(path):
    row = subprocess.run(["findmnt", "-n", "-o", "FSTYPE", "-T", str(path)],
                         capture_output=True, text=True, check=True, timeout=5)
    if row.stdout.strip() not in LOCAL_FILESYSTEMS:
        raise ValueError("Router and telemetry SQLite require node-local storage")
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError("Node-local runtime must be private to the allocation owner")


def runtime_preflight(destination):
    """Executed in a bounded helper subprocess on the assigned compute node."""
    from cohort_lab.workflow import _readiness
    from cohort_lab.hosted import release_manifest
    result = _readiness(ROOT / "data", need_pdf=True)
    if not result.get("ready"):
        write_json(destination / "runtime-readiness.json", result)
        raise RuntimeError("Actual CPU/browser/PDF runtime readiness failed")
    tex = shutil.which("pdflatex")
    if not tex:
        raise RuntimeError("The pinned pdflatex wrapper is missing")
    doc = destination / "tex-preflight"
    doc.mkdir()
    for name in ("labreport.sty", "labreport-b.sty", "longxiu-research-brief.sty"):
        shutil.copyfile(ROOT / "templates" / name, doc / name)
    (doc / "fixture.tex").write_text(r"""\documentclass[10pt]{article}
\usepackage{labreport}\usepackage{labreport-b}
\begin{document}\section{Runtime fixture}
Source Sans \textbf{bold}, \textit{italic}, \textbf{\textit{bold italic}}.
\[\operatorname{LTV}=\sum_{t=1}^{T}p_t r_t/(1+d)^t\]
\begin{tcolorbox}[title=Runtime]Synthetic fixture, not a fitted student result.\end{tcolorbox}
\begin{tikzpicture}\node[draw] (a) {Evidence};\node[draw,right=of a] (b) {Judgment};\draw[-{Latex}] (a)--(b);\end{tikzpicture}
\begin{tabular}{lr}\toprule Stage & Count\\\midrule Fixture & 1\\\bottomrule\end{tabular}
Last page: \pageref{LastPage}.\end{document}
""", encoding="utf-8")
    for i in range(2):
        done = subprocess.run([tex, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "fixture.tex"],
                              cwd=doc, capture_output=True, timeout=20)
        (doc / f"pass-{i}.log").write_bytes(done.stdout + b"\n" + done.stderr)
        if done.returncode:
            raise RuntimeError("Pinned TeX report-style fixture failed")
    pdf = (doc / "fixture.pdf").read_bytes()
    if not pdf.startswith(b"%PDF-") or len(pdf) < 1000:
        raise RuntimeError("TeX did not produce a PDF")
    result.update(tex_fixture_passed=True, tex_fixture_sha256=hashlib.sha256(pdf).hexdigest(),
                  release_hash=release_manifest()["release_hash"], observed_epoch=time.time())
    write_json(destination / "runtime-readiness.json", result)


def model_ready(plan, now):
    try:
        value = json.loads((plan.jobtmp / "model-status.json").read_text())
        return (value.get("ready") is True and value.get("ready_replicas") == 4
                and value.get("admission_capacity") == 8
                and 0 <= now - value.get("last_checked_at", 0) < 20
                and value.get("expires_at", 0) >= plan.deadline)
    except (OSError, ValueError):
        return False


def run(config_path):
    if sys.platform != "linux":
        raise RuntimeError("This pool must run inside the owned Linux Slurm allocation")
    os.umask(0o077)
    if config_path.stat().st_uid != os.getuid() or config_path.stat().st_mode & 0o077:
        raise ValueError("Pool configuration must be owner-only")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    jobtmp = Path(os.environ["STUDIO_NORTH_JOB_RUNTIME"])
    check_local_runtime(jobtmp)
    router = json.loads((jobtmp / "router-runtime.json").read_text())
    affinity = os.sched_getaffinity(0)
    plan = validate(config, os.environ, router, now=time.time(), affinity=affinity, topology=topology_for(affinity))
    bind_store(plan.runtime, config["session_id"], config["store_id"])
    write_json(plan.jobtmp / "pool-started.json", {"parent_job_id": plan.parent_job_id,
        "source_release_sha256": config["source_release_sha256"], "started_at": time.time()}, exclusive=True)
    owner = ProcessOwner(plan.runtime / "operator-logs" / plan.parent_job_id)
    owner.adopt_orphans()
    stopping = False
    def stop_requested(*_):
        nonlocal stopping
        stopping = True
    old_handlers = {s: signal.signal(s, stop_requested) for s in (signal.SIGTERM, signal.SIGINT)}
    clean_env = worker_environment(os.environ)
    clean_env.update(LAB_SESSION_ID=config["session_id"], LAB_ANALYSIS_STORE_ID=config["store_id"])
    router_env = dict(clean_env)
    router_env.update({k: v for k, v in os.environ.items() if k.startswith("STUDIO_NORTH_GPU") and k.endswith("_TOKEN")})
    identity = {"parent_job_id": plan.parent_job_id, "source_release_sha256": config["source_release_sha256"],
                "session_id": config["session_id"], "store_id": config["store_id"]}
    measurements = {}
    reason, last_backup = "startup", 0.0
    def health(ready, **extra):
        write_json(plan.jobtmp / "pool-health.json", identity | {"ready": ready, "observed_epoch": time.time(),
            "expires_at": plan.deadline, "analysis_slots": len(plan.analysis_cpus),
            "interactive_slots": config.get("interactive_workers", 8), **extra})
    def backup():
        stamp = str(time.time_ns())
        records = []
        for name in ("router.sqlite", "telemetry.sqlite"):
            saved = backup_sqlite(plan.jobtmp / name, plan.runtime / "operator-backups" / plan.parent_job_id / (stamp + "-" + name))
            if saved:
                records.append(saved)
        write_json(plan.runtime / "operator-backups" / plan.parent_job_id / (stamp + ".json"), identity | {"observed_epoch": time.time(), "databases": records})
    try:
        health(False, phase="runtime_preflight")
        probe = owner.spawn([sys.executable, "-m", "hosting.cpu_pool", "--runtime-preflight", str(plan.jobtmp)],
                            name="runtime-preflight", cpus=plan.helper_cpus, environment=clean_env)
        until = min(time.time() + 120, plan.deadline - 30)
        while probe["process"].poll() is None and not stopping and time.time() < until:
            owner.observe(); time.sleep(0.2)
        if stopping or probe["process"].poll() != 0:
            raise RuntimeError("Bounded runtime preflight did not pass")
        readiness = json.loads((plan.jobtmp / "runtime-readiness.json").read_text())
        if not readiness.get("ready") or not readiness.get("tex_fixture_passed") or readiness.get("release_hash") != config["release_hash"]:
            raise RuntimeError("Runtime readiness is not bound to the frozen release")
        write_json(plan.runtime / "operator-receipts" / plan.parent_job_id / "runtime-readiness.json", identity | readiness)
        daemon = owner.spawn([sys.executable, "-m", "hosting.nemotron_router", "--config", str(plan.router_path), "--serve"],
                             name="nemotron-router", cpus=plan.helper_cpus, environment=router_env)
        until = min(time.time() + 60, plan.deadline - 30)
        while not stopping and time.time() < until and daemon["process"].poll() is None and not model_ready(plan, time.time()):
            owner.observe(); time.sleep(0.25)
        if stopping or daemon["process"].poll() is not None or not model_ready(plan, time.time()):
            raise RuntimeError("Router has no fresh four-replica health attestation")
        workers = []
        for lane, count in (("analysis", len(plan.analysis_cpus)), ("interactive", config.get("interactive_workers", 8))):
            for i in range(1, count + 1):
                if stopping or time.time() >= plan.deadline - 30:
                    raise RuntimeError("Pool startup was interrupted")
                spec = worker_config(plan, lane, i)
                path = plan.jobtmp / "workers" / (spec["worker_id"] + ".json")
                write_json(path, spec, exclusive=True)
                cores = (plan.analysis_cpus[i - 1],) if lane == "analysis" else plan.helper_cpus
                record = owner.spawn([sys.executable, "-m", "hosting.bluechip_worker", "--config", str(path)],
                                     name=spec["worker_id"], cpus=cores, environment=clean_env)
                record["lane"] = lane
                workers.append(record)
        reason = "running"
        while not stopping and time.time() < plan.deadline:
            now = time.time(); owner.observe()
            if daemon["process"].poll() is not None:
                raise RuntimeError("The shared router stopped; interpretation requires operator recovery")
            alive, inventory = worker_inventory(owner, workers, plan.runtime / "operator-receipts" / plan.parent_job_id, identity)
            registered = 0
            for record in alive:
                try:
                    value = json.loads((plan.runtime / (record["name"] + "-health.json")).read_text())
                    fresh = 0 <= now - value.get("heartbeat", 0) < 45 and value.get("release_hash") == config["release_hash"]
                    registered += bool(fresh)
                    job = value.get("job_id")
                    if fresh and record["lane"] == "analysis" and job:
                        item = measurements.setdefault(job, {"worker_id": record["name"], "first_observed": now, "peak_tree_rss_bytes": 0})
                        item.update(last_observed=now, elapsed_observed_seconds=now-item["first_observed"],
                                    peak_tree_rss_bytes=max(item["peak_tree_rss_bytes"], record["current_rss_bytes"]))
                except (OSError, ValueError):
                    pass
            capacity = inventory['remaining_analysis_slots'] > 0 and inventory['remaining_interactive_slots'] > 0
            health(capacity and registered == len(alive) and model_ready(plan, now), phase="running",
                   registered_workers=registered, **inventory)
            write_json(plan.runtime / "operator-receipts" / plan.parent_job_id / "analysis-memory-samples.json", identity | {
                "observed_epoch": now, "sampling_seconds": 3, "method": "sum of Linux process-tree RSS; shared pages may be counted more than once",
                "not_exact_peak": True, "admission_change_authorized": False, "jobs": measurements})
            if now - last_backup >= 60:
                try:
                    backup(); last_backup = now
                except (OSError, sqlite3.Error, TimeoutError, RuntimeError) as exc:
                    write_json(plan.runtime / "operator-receipts" / plan.parent_job_id / "backup-error.json", identity | {
                        "observed_epoch": now, "error_type": type(exc).__name__})
                    last_backup = now
            time.sleep(min(3, max(0, plan.deadline - time.time())))
        reason = "signal" if stopping else "deadline"
        return 0
    except BaseException as exc:
        reason = type(exc).__name__
        raise
    finally:
        with contextlib.suppress(OSError):
            health(False, phase="stopping", reason=reason)
        owner.stop(grace=8)
        try:
            backup()
        except (OSError, sqlite3.Error, TimeoutError, RuntimeError) as exc:
            write_json(plan.runtime / "operator-receipts" / plan.parent_job_id / "final-backup-error.json", identity | {"error_type": type(exc).__name__})
        for record in owner.children:
            if record.get("exit_recorded"):
                continue
            write_json(plan.runtime / "operator-receipts" / plan.parent_job_id / (record["name"] + "-exit.json"), identity | {
                "name": record["name"], "pid": record["process"].pid, "returncode": record["process"].poll(),
                "started_at": record["started_at"], "ended_at": time.time(), "cpus": record["cpus"],
                "peak_observed_tree_rss_bytes": record["peak_rss_bytes"], "reason": reason, "restarted": False})
        health(False, phase="stopped", reason=reason)
        for sig, previous in old_handlers.items():
            signal.signal(sig, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", type=Path)
    group.add_argument("--runtime-preflight", type=Path)
    args = parser.parse_args()
    if args.runtime_preflight:
        runtime_preflight(args.runtime_preflight)
        return 0
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
