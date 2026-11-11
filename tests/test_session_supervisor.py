import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from hosting import session_supervisor as owner


class Clock:
    def __init__(self):
        self.value = 1000.0
        self.elapsed = 0.0

    def wall(self):
        return self.value

    def mono(self):
        return self.elapsed

    def wait(self, seconds):
        self.value += seconds
        self.elapsed += seconds


class Child:
    next_pid = 100

    def __init__(self, clock, failure_at=None):
        Child.next_pid += 1
        self.pid = Child.next_pid
        self.clock = clock
        self.failure_at = failure_at
        self.stopped_at = None

    def poll(self):
        if self.stopped_at is not None:
            return -15
        if self.failure_at is not None and self.clock.elapsed >= self.failure_at:
            return 7
        return None

    def wait(self, timeout=None):
        assert self.poll() is not None
        return self.poll()


def config(tmp_path, expiry=1010):
    frozen = tmp_path / 'frozen.py'
    frozen.write_text('# immutable fixture')
    return {'session_id': 'fixture-session', 'expires_at': expiry,
            'state_dir': str(tmp_path / 'state'),
            'frozen_files': {str(frozen): hashlib.sha256(frozen.read_bytes()).hexdigest()},
            'components': [{'name': name, 'command': [sys.executable, str(frozen)],
                            'cwd': str(tmp_path), 'session_id': 'fixture-session',
                            'expires_at': expiry} for name in ('bridge', 'debrief')]}


def exercise(tmp_path, failed=None, launch_failed=None, wait_hook=None, stopping=None):
    clock = Clock()
    plan = owner.validate(config(tmp_path), now=clock.wall(), windows=False)
    children = {}
    launches = []

    def spawn(plan, component, log):
        name = component['name']
        launches.append(name)
        if name == launch_failed:
            raise OSError('fixture executable unavailable')
        child = Child(clock, failure_at=2 if name == failed else None)
        children[name] = child
        return child

    def stop(child, **kwargs):
        if child.poll() is None:
            child.stopped_at = clock.elapsed

    def wait(seconds):
        clock.wait(seconds)
        if wait_hook:
            wait_hook(clock)

    result = owner.supervise(plan, spawn=spawn, stop=stop, wall=clock.wall,
                             monotonic=clock.mono, wait=wait, stopping=stopping)
    return result, children, launches, clock, plan


@pytest.mark.parametrize('failed', ['bridge', 'debrief'])
def test_failed_component_does_not_kill_or_restart_healthy_sibling(tmp_path, failed):
    code, children, launches, clock, plan = exercise(tmp_path, failed=failed)
    healthy = 'debrief' if failed == 'bridge' else 'bridge'
    assert code == 1
    assert children[healthy].stopped_at == 10
    assert launches == ['bridge', 'debrief']  # No replay or restart.
    alert = json.loads((plan.state_dir / 'operator-attention.json').read_text())
    assert alert['failures'][failed]['exit_code'] == 7
    assert alert['healthy_components_preserved']


def test_launch_failure_keeps_successful_component_until_deadline(tmp_path):
    code, children, launches, clock, plan = exercise(tmp_path, launch_failed='bridge')
    assert code == 1 and children['debrief'].stopped_at == 10


def test_status_disk_error_does_not_stop_work(tmp_path, monkeypatch):
    actual = owner.write_json

    def intermittent(path, value, **kwargs):
        if Path(path).name == 'status.json':
            raise OSError('fixture observation storage unavailable')
        return actual(path, value, **kwargs)

    monkeypatch.setattr(owner, 'write_json', intermittent)
    code, children, launches, clock, plan = exercise(tmp_path)
    assert code == 0 and all(c.stopped_at == 10 for c in children.values())
    assert json.loads((plan.state_dir / 'exit.json').read_text())['reason'] == 'deadline'


def test_backwards_clock_cannot_extend_window(tmp_path):
    def rewind(clock):
        if clock.elapsed == 2:
            clock.value -= 3600
    _, children, _, clock, _ = exercise(tmp_path, wait_hook=rewind)
    assert clock.elapsed == 10 and all(c.stopped_at == 10 for c in children.values())


def test_cancel_stops_both_owned_components(tmp_path):
    stopping = threading.Event()
    _, children, _, clock, plan = exercise(tmp_path, stopping=stopping,
        wait_hook=lambda clock: stopping.set() if clock.elapsed >= 3 else None)
    assert all(c.stopped_at == 3 for c in children.values())
    assert json.loads((plan.state_dir / 'exit.json').read_text())['reason'] == 'cancelled'


def test_second_owner_cannot_start_any_children(tmp_path):
    _, _, _, clock, plan = exercise(tmp_path)
    calls = []
    with pytest.raises(FileExistsError):
        owner.supervise(plan, spawn=lambda *a: calls.append(a), wall=lambda: 1000)
    assert not calls


@pytest.mark.parametrize('mutation', ['hash', 'deadline', 'session', 'empty_hashes'])
def test_invalid_preflight_precedes_any_launch(tmp_path, mutation):
    value = config(tmp_path)
    if mutation == 'hash':
        Path(next(iter(value['frozen_files']))).write_text('changed')
    elif mutation == 'deadline':
        value['components'][1]['expires_at'] += 60
    elif mutation == 'session':
        value['components'][1]['session_id'] = 'wrong-session'
    else:
        value['frozen_files'] = {}
    with pytest.raises(ValueError):
        owner.validate(value, now=1000, windows=False)
    assert not (tmp_path / 'state').exists()


def test_credentials_stay_with_their_own_component(monkeypatch):
    monkeypatch.setenv('BLUECHIP_METERED_SERVICE_TOKEN', 'review-fixture')
    monkeypatch.setenv('STUDIO_NORTH_GPU1_TOKEN', 'gpu-fixture')
    assert 'BLUECHIP_METERED_SERVICE_TOKEN' not in owner.child_environment('bridge')
    assert 'STUDIO_NORTH_GPU1_TOKEN' not in owner.child_environment('debrief')


def test_windows_requires_hash_bound_gui_launcher(tmp_path):
    with pytest.raises(ValueError, match='pythonw'):
        owner.validate(config(tmp_path), now=1000, windows=True)


def test_expired_plan_never_creates_intent(tmp_path):
    plan = owner.validate(config(tmp_path), now=1000, windows=False)
    with pytest.raises(ValueError, match='expired'):
        owner.supervise(plan, wall=lambda: 1020)
    assert not plan.state_dir.exists()


def test_cleanup_error_does_not_skip_sibling_cleanup(tmp_path):
    clock = Clock()
    plan = owner.validate(config(tmp_path), now=1000, windows=False)
    children = {}
    def spawn(plan, component, log):
        child = Child(clock)
        children[component['name']] = child
        return child
    def stop(child, *, force=False):
        if child is children['bridge'] and not force:
            # The process was stopped but the control acknowledgment failed.
            child.stopped_at = clock.elapsed
            raise OSError('fixture lost termination acknowledgment')
        child.stopped_at = clock.elapsed
    assert owner.supervise(plan, spawn=spawn, stop=stop, wall=clock.wall,
                           monotonic=clock.mono, wait=clock.wait) == 1
    assert children['debrief'].stopped_at == 10
