import copy
import hashlib
import json
import threading
import time

from hosting.bluechip_worker import deliver_result, redeliver_until


def fixture(tmp_path):
    path=tmp_path/'report.pdf';path.write_bytes(b'fixture report')
    body={'result':{'packet':{'artifacts':[{'artifact_id':'artifact','name':'report.pdf','mime':'application/pdf',
          'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'local_path':str(path)}]}}}
    return {'id':'job-0001'},body


class LostAcknowledgment:
    def __init__(self):self.calls=[];self.status='running'
    def request(self,path,body=None,**kwargs):
        self.calls.append((path,body,kwargs))
        if 'job_status' in path:return {'status':self.status}
        if '/finish' in path:
            self.status='completed'
            raise TimeoutError('The server committed, but the acknowledgment was lost')
        return {'ok':True}


def test_delivery_recovers_lost_ack_without_reupload_or_execution(tmp_path):
    job,body=fixture(tmp_path);saved=copy.deepcopy(body);broker=LostAcknowledgment()
    result=tmp_path/'result.json';result.write_text(json.dumps(body))
    # Event.wait is immediate in this fixture; it does not modify the recovery logic.
    class NoWait(threading.Event):
        def wait(self,timeout=None):return self.is_set()
    live={}
    assert redeliver_until(broker,job,result,tmp_path,deadline=time.time()+5,live=live,stopping=NoWait())
    assert len([x for x in broker.calls if '/artifact' in x[0]])==1
    assert len([x for x in broker.calls if '/finish' in x[0]])==1
    assert live['cpu']=='ready' and (tmp_path/'delivered.json').is_file()
    assert json.loads(result.read_text())==saved


def test_delivery_rejects_changed_artifact_before_upload(tmp_path):
    import pytest
    job,body=fixture(tmp_path);broker=LostAcknowledgment()
    (tmp_path/'report.pdf').write_bytes(b'changed')
    with pytest.raises(RuntimeError,match='Artifact changed'):deliver_result(broker,job,body)
    assert len(broker.calls)==1 and broker.status=='running'


def test_display_progress_failure_never_fails_work(tmp_path,monkeypatch):
    from pathlib import Path
    from hosting.nemotron_router import publish_progress
    monkeypatch.setattr(Path,'write_text',lambda *a,**k:(_ for _ in ()).throw(PermissionError('fixture')))
    publish_progress(tmp_path/'progress.json',{'position':4})
    assert not (tmp_path/'progress.json').exists()
