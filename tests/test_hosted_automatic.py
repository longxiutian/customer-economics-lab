import json
import time
import uuid

import pytest
from reportlab.pdfgen.canvas import Canvas

from cohort_lab import automatic, hosted
from cohort_lab.workflow import WorkflowError
from scripts import run_automatic
from hosting.telemetry import Telemetry
from hosting.student_debrief import freeze


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(hosted, 'release_manifest', lambda: {'release_hash': 'fixture-release'})
    monkeypatch.setattr(automatic, 'implementation_snapshot', lambda: {})
    monkeypatch.setattr(automatic, 'verify_frozen_inputs', lambda _: {})

    def run(output, **kwargs):
        calls.append((output, kwargs))
        output.mkdir(parents=True)
        (output/'automatic_run.json').write_text(json.dumps({'implementation': {}, 'inputs': {},
            'status': 'complete', 'completed_stages': list(range(8))}))
        (output/'model_summary.json').write_text('{"fixture":true}')
        report=output/'report';report.mkdir()
        pdf=Canvas(str(report/'customer-economics-report.pdf'))
        for _ in range(15):
            pdf.drawString(20, 700, 'Studio North fixture report');pdf.showPage()
        pdf.save()
        (report/'customer-economics-report.tex').write_text('fixture source')
    monkeypatch.setattr(run_automatic, 'run', run)
    adapter=hosted.HostedLesson(tmp_path, automatic_test_until=time.time()+3600,
        interpreter=lambda *a: {'status': 'completed', 'text': 'Fixture interpretation'})
    return adapter,calls


def request(run_id=None, **payload):
    return {'id': str(uuid.uuid4()), 'run_id': run_id or str(uuid.uuid4()),
            'release_hash': 'fixture-release', 'checkpoint': -1,
            'payload': {'action': 'start', 'mode': 'automatic-test', 'message': automatic.START_MESSAGE, **payload}}


def test_automatic_report_fresh_fit_idempotency_and_student_isolation(fixture):
    adapter,calls=fixture
    job=request()
    result=adapter.execute(job)
    packet=result['packet']
    assert result['execution']['fresh_fit'] and packet['validation']['report_complete']
    assert not packet['validation']['workflow_complete']  # Review is still separate.
    assert packet['guided_participation'] is False and packet['choices']=={}
    assert 'all_checkpoints' not in packet['validation']['checks']
    assert adapter.execute(job)==result and len(calls)==1
    adapter.execute(request())
    assert len(calls)==2 and calls[0][0]!=calls[1][0]
    assert calls[0][1]['prompt']==automatic.START_MESSAGE and calls[0][1]['hosted'] is True
    assert not (calls[0][0]/'lesson_state.json').exists()
    follow=request(job['run_id'],action='message',message='What does iCAC mean?')
    follow['payload'].pop('mode');follow['checkpoint']=18
    assert adapter.execute(follow)['packet']['step']==18 and len(calls)==2
    assert not adapter.execute(follow)['execution']['fresh_fit']


def test_disabled_window_and_nonexplicit_request_do_not_run(fixture):
    adapter,calls=fixture
    adapter.automatic_test_until=0
    with pytest.raises(WorkflowError,match='not enabled'):adapter.execute(request())
    adapter.automatic_test_until=time.time()+3600
    with pytest.raises(WorkflowError,match='explicit student'):adapter.execute(request(message='Start my lab'))
    assert calls==[]


def test_automatic_cannot_replace_guided_workspace(fixture):
    adapter,calls=fixture
    job=request()
    _,output,_=adapter.locations(job['run_id']);output.mkdir(parents=True)
    (output/'lesson_state.json').write_text('{}')
    with pytest.raises(WorkflowError,match='guided progress'):adapter.execute(job)
    assert calls==[]


def test_automatic_debrief_records_actual_request_without_teaching_claims(fixture,tmp_path):
    adapter,_=fixture
    job=request();adapter.execute(job)
    _,_,receipts=adapter.locations(job['run_id'])
    ledger=Telemetry(tmp_path/'events.sqlite')
    ledger.ingest_receipt(json.loads((receipts/(job['id']+'.json')).read_text()),session_id='test-session')
    snapshot=freeze(ledger,run_id=job['run_id'],session_id='test-session',path=tmp_path/'evidence.json')
    assert snapshot['metrics']['execution_mode']=='automatic-test'
    assert snapshot['metrics']['saved_judgments']==0 and snapshot['metrics']['checkpoints_observed']==[]
    assert snapshot['metrics']['fresh_fits']==1
    assert any(e['text']==automatic.START_MESSAGE for e in snapshot['evidence'])
    assert 'analyst-authored' in snapshot['coverage']['execution_mode']
