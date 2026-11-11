"""One bounded operator owner for independent bridge and debrief process trees.

No visible terminal windows. No Slurm submissions, provider calls, job replay,
automatic component restart, or deadline extension. Use an operator-owned JSON
configuration outside Git and the maintained Windows hidden launcher.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Plan:
    session_id: str
    expires_at: float
    state_dir: Path
    components: tuple
    launcher: tuple
    config_sha256: str


def validate(config, *, now, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    session = config.get('session_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', session):
        raise ValueError('An explicit session identity is required')
    expiry = float(config['expires_at'])
    if not math.isfinite(expiry) or not now < expiry <= now + 5 * 3600 + 120:
        raise ValueError('Session expiry must be future and no more than five hours away')
    state = Path(config['state_dir'])
    if not state.is_absolute():
        raise ValueError('Operator state directory must be absolute')
    components = config.get('components', [])
    if len(components) != 2 or {c.get('name') for c in components} != {'bridge', 'debrief'}:
        raise ValueError('Exactly one bridge and one debrief owner are required')
    for component in components:
        command = component.get('command')
        if (not isinstance(command, list) or not command or
                not all(isinstance(x, str) and x and '\x00' not in x for x in command)):
            raise ValueError('Component commands must be explicit argument arrays')
        if not Path(command[0]).is_absolute() or not Path(command[0]).is_file():
            raise ValueError('Component executable must exist at an absolute path')
        if not Path(component['cwd']).is_absolute() or not Path(component['cwd']).is_dir():
            raise ValueError('Component working directory must exist')
        if float(component['expires_at']) != expiry:
            raise ValueError('Every component must share the original fixed expiry')
        if component.get('session_id') != session:
            raise ValueError('Component session identity mismatch')
    # Bind scripts AND private worker configurations before any child starts.
    frozen = config.get('frozen_files', {})
    if not frozen:
        raise ValueError('Frozen source and configuration hashes are required')
    for filename, expected in frozen.items():
        path = Path(filename)
        if not path.is_absolute() or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError('Invalid frozen file binding')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen source or configuration changed before launch')
    launcher = tuple(config.get('windows_launcher', []))
    if windows:
        if (len(launcher) != 2 or Path(launcher[0]).name.lower() != 'pythonw.exe' or
                Path(launcher[1]).name != 'hidden_launcher.py' or
                any(not Path(p).is_absolute() or not Path(p).is_file() for p in launcher) or
                launcher[1] not in frozen):
            raise ValueError('The hash-bound maintained pythonw Job Object launcher is required')
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return Plan(session, expiry, state, tuple(components), launcher, digest)


def child_environment(name):
    environment = dict(os.environ)
    if name == 'debrief':
        environment = {k: v for k, v in environment.items()
                       if not (k.startswith('STUDIO_NORTH_GPU') and k.endswith('_TOKEN'))}
    else:
        environment.pop('BLUECHIP_METERED_SERVICE_TOKEN', None)
    return environment


def spawn_component(plan, component, log):
    command = list(component['command'])
    if os.name == 'nt':
        command = [*plan.launcher, *command]
    return subprocess.Popen(command, cwd=component['cwd'], env=child_environment(component['name']),
                            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                            start_new_session=os.name != 'nt')


def stop_component(process, *, force=False):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # The child is a dedicated maintained pythonw Job Object owner, so closing
        # it terminates this component's descendants without touching its sibling.
        process.kill() if force else process.terminate()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)


def supervise(plan, *, stopping=None, spawn=spawn_component, stop=stop_component,
              wall=time.time, monotonic=time.monotonic, wait=None):
    stopping = stopping if stopping is not None else threading.Event()
    wait = wait or stopping.wait
    started = wall()
    if started >= plan.expires_at:
        raise ValueError('Session has expired; nothing was launched')
    # The monotonic ceiling prevents a backwards wall-clock adjustment extending
    # the authorized window. A forwards adjustment also stops at the wall expiry.
    ceiling = monotonic() + plan.expires_at - started
    intent = {'session_id': plan.session_id, 'expires_at': plan.expires_at,
              'started_at': started, 'pid': os.getpid(), 'config_sha256': plan.config_sha256,
              'automatic_restart': False, 'provider_replay': False}
    write_json(plan.state_dir / 'launch-intent.json', intent, exclusive=True)
    processes = {}
    logs = []
    failures = {}
    incident = None
    reason = 'deadline'

    def snapshot():
        return {**intent, 'observed_at': wall(), 'phase': 'degraded' if failures else 'running',
                'service_readiness_source': 'authenticated_broker_status_not_process_liveness',
                'components': {c['name']: {'pid': processes[c['name']].pid if c['name'] in processes else None,
                                          'exit_code': processes[c['name']].poll() if c['name'] in processes else None,
                                          'failure': failures.get(c['name'])} for c in plan.components}}

    def persist(name, value):
        # Observational logging is not permission to kill healthy workers.
        try:
            write_json(plan.state_dir / name, value)
        except (OSError, ValueError) as error:
            print(json.dumps({'event': 'supervisor_receipt_failed', 'receipt': name,
                              'error_type': type(error).__name__}), file=sys.stderr, flush=True)

    try:
        for component in plan.components:
            name = component['name']
            try:
                log = (plan.state_dir / (name + '.log')).open('ab')
                logs.append(log)
                processes[name] = spawn(plan, component, log)
            except (OSError, subprocess.SubprocessError) as error:
                failures[name] = {'reason': 'launch_failed', 'error_type': type(error).__name__}
        while wall() < plan.expires_at and monotonic() < ceiling and not stopping.is_set():
            for name, process in processes.items():
                code = process.poll()
                if code is not None and name not in failures:
                    failures[name] = {'reason': 'component_exited', 'exit_code': code, 'at': wall()}
            state = snapshot()
            persist('status.json', state)
            if failures and incident != failures:
                incident = json.loads(json.dumps(failures))
                # This stable operator alert is separate from student readiness.
                # It contains no credentials, prompts, or private argument arrays.
                persist('operator-attention.json', {'session_id': plan.session_id, 'at': wall(),
                        'failures': failures, 'healthy_components_preserved': True,
                        'action': 'Reconcile the failed component; do not restart the session or replay student jobs.'})
            if not any(p.poll() is None for p in processes.values()):
                reason = 'all_components_stopped'
                break
            wait(min(1.0, max(0.0, plan.expires_at - wall()), max(0.0, ceiling - monotonic())))
        if stopping.is_set():
            reason = 'cancelled'
    finally:
        # Stop all owned trees on cancellation/deadline, including failed starts
        # that left a successfully started sibling. No Slurm job is touched here.
        for name, process in processes.items():
            try:
                stop(process)
            except OSError as error:
                failures[name] = {'reason': 'termination_failed', 'error_type': type(error).__name__}
        for name, process in processes.items():
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    stop(process, force=True)
                    process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired) as error:
                    failures[name] = {'reason': 'cleanup_incomplete', 'error_type': type(error).__name__}
        persist('exit.json', {**snapshot(), 'phase': 'stopped', 'reason': reason,
                             'ended_at': wall(), 'automatic_restart': False})
        for log in logs:
            log.close()
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    plan = validate(json.loads(args.config.read_text(encoding='utf-8')), now=time.time())
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    return supervise(plan, stopping=stopping)


if __name__ == '__main__':
    raise SystemExit(main())
