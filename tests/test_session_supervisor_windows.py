"""Opt-in real Windows fixtures; no network, model, email, or scheduler calls.

Set STUDIO_NORTH_TEST_HIDDEN_LAUNCHER to the maintained hidden_launcher.py.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = os.environ.get('STUDIO_NORTH_TEST_HIDDEN_LAUNCHER')
pytestmark = pytest.mark.skipif(os.name != 'nt' or not LAUNCHER,
    reason='Requires explicit maintained Windows Job Object launcher')

FIXTURE = '''import json, os, pathlib, subprocess, sys, time
name, directory, mode = sys.argv[1:]
root = pathlib.Path(directory)
(root/(name+'.pid')).write_text(str(os.getpid()))
if mode == 'grandchild':
    time.sleep(40)
    raise SystemExit(0)
child = subprocess.Popen([sys.executable, __file__, name+'-child', directory, 'grandchild'],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if mode in ('failure', 'success'):
    time.sleep(.3)
    raise SystemExit(7 if mode == 'failure' else 0)
for _ in range(400):
    (root/(name+'.pulse')).write_text(str(time.time()))
    time.sleep(.1)
'''


@pytest.mark.parametrize('mode', ['failure', 'success', 'cancel'])
def test_real_component_isolation_deadline_and_cancellation(tmp_path, mode):
    launcher = Path(LAUNCHER)
    spec = importlib.util.spec_from_file_location('window_observer_fixture', launcher.with_name('verify_windowless.py'))
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    fixture = tmp_path / 'fixture.py'
    fixture.write_text(FIXTURE)
    now = time.time()
    expiry = now + (15 if mode == 'cancel' else 5)
    config = {'session_id': 'window-fixture-' + mode, 'expires_at': expiry,
              'state_dir': str(tmp_path / 'state'),
              'windows_launcher': [str(Path(sys.executable).with_name('pythonw.exe')), str(launcher)],
              'frozen_files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (launcher, fixture, ROOT / 'hosting/session_supervisor.py')},
              'components': [{'name': name, 'command': [sys.executable, str(fixture), name, str(tmp_path),
                               mode if name == 'bridge' and mode != 'cancel' else 'wait'],
                               'cwd': str(ROOT), 'session_id': 'window-fixture-' + mode,
                               'expires_at': expiry} for name in ('bridge', 'debrief')]}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    baseline, seen = observer.windows(), set()
    command = [str(Path(sys.executable).with_name('pythonw.exe')), str(launcher),
               sys.executable, '-m', 'hosting.session_supervisor', '--config', str(path)]
    child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    cancelled = False
    try:
        deadline = time.monotonic() + 12
        while child.poll() is None and time.monotonic() < deadline:
            seen.update(observer.windows() - baseline)
            if mode == 'cancel' and len(list(tmp_path.glob('*.pid'))) == 4:
                child.terminate()  # Closing the outer Job Object must own all descendants.
                cancelled = True
            time.sleep(.02)
        assert child.poll() is not None, 'Fixture owner exceeded its bounded deadline'
        pids = [int(p.read_text()) for p in tmp_path.glob('*.pid')]
        assert len(pids) == 4
        until = time.monotonic() + 3
        while any(observer.alive(pid) for pid in pids) and time.monotonic() < until:
            time.sleep(.02)
        assert not any(observer.alive(pid) for pid in pids), 'An owned descendant survived cleanup'
        leaked = [x for x in seen if x[2] in ('ConsoleWindowClass', 'CASCADIA_HOSTING_WINDOW_CLASS')]
        assert not leaked, 'A new visible terminal window appeared'
        if mode == 'cancel':
            assert cancelled
        else:
            assert child.returncode == 1  # An early bridge exit is an explicit degraded result.
            pulse = float((tmp_path / 'debrief.pulse').read_text())
            assert pulse >= expiry - .5, 'Healthy review component was stopped with failed bridge'
            receipt = json.loads((tmp_path / 'state/exit.json').read_text())
            assert receipt['reason'] == 'deadline'
            assert receipt['components']['bridge']['exit_code'] == (7 if mode == 'failure' else 0)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
