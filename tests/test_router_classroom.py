import concurrent.futures
import threading
from pathlib import Path

import pytest

from hosting.inference_router import FairRouter
from hosting.telemetry import Telemetry


def make(tmp_path, **kwargs):
    specs=[{'id':f'gpu-{i}','capacity':2,'revision':'pin','manifest_hash':'manifest'} for i in range(4)]
    r=FairRouter(tmp_path/'queue.sqlite',Telemetry(tmp_path/'events.sqlite'),specs,config_hash='config',expires_at=10000,clock=lambda:1000,**kwargs)
    for s in specs:r.set_health(s['id'],revision='pin',manifest_hash='manifest',config_hash='config',verified_at=1000,expires_at=10000,ready=True)
    return r


def test_45_concurrent_starts_are_bounded_and_ranked(tmp_path):
    r=make(tmp_path,max_queue=45)
    def submit(i):return r.submit(request_id=f'job-{i}',run_id=f'run-{i}',session_id='session',payload={'question':'start'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=45) as p:
        records=list(p.map(submit,range(45)))
    ranks=[r.poll(f'job-{i}',run_id=f'run-{i}')['progress']['position'] for i in range(45)]
    assert sorted(ranks)==list(range(1,46))
    with pytest.raises(ValueError,match='full'):submit(45)
    for i in range(45):assert submit(i)['id']==f'job-{i}'
    tickets=[r.claim() for _ in range(8)]
    assert all(tickets) and r.claim() is None
    assert len({t['run_id'] for t in tickets})==8
    with pytest.raises(KeyError):r.poll('job-0',run_id='run-1')
    remaining=[r.poll(f'job-{i}',run_id=f'run-{i}')['progress']['position'] for i in range(45)]
    assert sorted(x for x in remaining if x is not None)==list(range(1,38))
    dispatched={t['id'] for t in tickets}
    while tickets:
        for t in tickets:r.finish(t,outcome='completed',response={'usage':{'prompt_tokens':5,'completion_tokens':2}})
        tickets=[]
        while t:=r.claim():
            assert t['id'] not in dispatched
            dispatched.add(t['id']);tickets.append(t)
    assert len(dispatched)==45


def test_fair_position_excludes_own_inflight_and_rotates(tmp_path):
    r=make(tmp_path)
    for key,run in [('a1','a'),('a2','a'),('b1','b')]:r.submit(request_id=key,run_id=run,session_id='s',payload={})
    assert r.poll('a2',run_id='a')['progress']['position'] is None
    first=r.claim();assert first['id']=='a1'
    assert r.poll('a2',run_id='a')['progress']['blocked_by_previous_request']
    r.finish(first,outcome='completed')
    assert r.poll('b1',run_id='b')['progress']['position']==1
    assert r.poll('a2',run_id='a')['progress']['position']==2


def test_expiry_and_telemetry_failure_do_not_replay(tmp_path):
    r=make(tmp_path)
    r.submit(request_id='done',run_id='a',session_id='s',payload={})
    t=r.claim()
    original=r.telemetry.append
    r.telemetry.append=lambda **kw: (_ for _ in ()).throw(OSError('fixture outage'))
    r.finish(t,outcome='completed',response={'usage':{'prompt_tokens':3,'completion_tokens':1}})
    assert r.poll('done',run_id='a')['state']=='completed'
    assert r.last_export_error=='OSError'
    r.telemetry.append=original;r.try_export()
    assert r.last_export_error is None and len(r.telemetry.events('a','s'))==1
    r.submit(request_id='queued',run_id='b',session_id='s',payload={'_deadline':1200})
    r.clock=lambda:1100
    assert r.poll('queued',run_id='b')['state']=='expired'
    r.clock=lambda:10001
    assert r.submit(request_id='done',run_id='a',session_id='s',payload={})['state']=='completed'
    with pytest.raises(ValueError,match='ended'):r.submit(request_id='late',run_id='c',session_id='s',payload={})


def test_executor_rejection_is_known_undispatched(tmp_path):
    r=make(tmp_path)
    r.submit(request_id='job',run_id='a',session_id='s',payload={})
    with concurrent.futures.ThreadPoolExecutor() as pool:pass
    r.dispatch_available(pool,lambda *_:pytest.fail('must not invoke'))
    row=r.poll('job',run_id='a')
    assert row['state']=='failed' and row['result']['response']['error_type']=='ExecutorRejectedBeforeInvocation'


def test_queue_is_bound_to_one_host_session_and_profile(tmp_path,monkeypatch):
    r=make(tmp_path,session_id='session-a')
    with pytest.raises(ValueError,match='Foreign router session'):
        r.submit(request_id='job',run_id='run',session_id='session-b',payload={})
    with pytest.raises(ValueError,match='session_id changed'):make(tmp_path,session_id='session-b')
    monkeypatch.setattr('hosting.inference_router.socket.gethostname',lambda:'another-host')
    with pytest.raises(ValueError,match='host changed'):make(tmp_path,session_id='session-a')
