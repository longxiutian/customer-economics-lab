import hashlib
import json
from pathlib import Path
import uuid

import pytest

from cohort_lab.debrief import initialize,snapshot,prepare
from cohort_lab.lab_close import handle,read,binding
from cohort_lab.instructor_feedback import deliver,status,_read


def workspace(tmp_path,route='personal'):
    (tmp_path/'lesson_state.json').write_text(json.dumps({'completed_step':2,'messages':[],'implementation':{}}))
    initialize(tmp_path,route=route,harness='Codex')
    return tmp_path


def accepted(payload,client):
    return 200,{'ok':True,'feedback_id':'fixture-feedback','workspace_id':payload['workspace_id'],'close_id':payload['close_id'],
                'participant_id':client['client_id'],'identity_kind':'lab_install','received_at':123}


def test_only_noticed_ended_feedback_is_submitted_and_never_enters_evidence(tmp_path):
    out=workspace(tmp_path);calls=[]
    def send(p,c):calls.append(p);return accepted(p,c)
    assert deliver(out,transport=send)['status']=='not_submitted' and calls==[]
    handle(out,'end lab')
    assert deliver(out,transport=send)['status']=='not_submitted' and calls==[]
    reply='Signed fixture: 雪\r\nKeep my spaces.  '
    handle(out,reply)
    before=binding(out)
    assert deliver(out,transport=send)['status']=='delivered'
    assert len(calls)==1 and calls[0]['reply']==reply
    assert calls[0]['reply_sha256']==hashlib.sha256(reply.encode()).hexdigest()
    assert calls[0]['workspace_id']==json.loads((out/'usage/session.json').read_text())['run_id']
    assert reply not in json.dumps(snapshot(out),ensure_ascii=False)
    assert binding(out)==before
    deliver(out,transport=send);assert len(calls)==1


def test_failure_does_not_block_debrief_and_reopen_preserves_pending_cycle(tmp_path):
    out=workspace(tmp_path)
    handle(out,'end simulation');handle(out,'Fixture feedback')
    assert status(out)['status']=='pending'
    assert Path(prepare(out)['debrief']).is_file()
    original=_read(out/'usage/instructor-feedback.json')['entries'][0]['payload']['close_id']
    handle(out,'continue lab');handle(out,'end lab');handle(out,'skip feedback')
    entries=_read(out/'usage/instructor-feedback.json')['entries']
    assert len(entries)==2 and entries[0]['payload']['close_id']==original
    delivered=[]
    def send(p,c):delivered.append(p);return accepted(p,c)
    deliver(out,transport=send);deliver(out,transport=send)
    assert len(delivered)==2 and delivered[1]['disposition']=='declined' and delivered[1]['reply']==''
    assert _read(out/'usage/instructor-feedback.json')['entries'][0]['status']=='delivered'


@pytest.mark.parametrize('route',['longleaf','unknown'])
def test_hosted_and_unknown_routes_never_make_local_network_calls(tmp_path,route):
    if route=='longleaf':out=workspace(tmp_path,route)
    else:out=tmp_path
    handle(out,'end lab');handle(out,'Fixture feedback')
    def forbidden(*args):pytest.fail('hosted/unknown route contacted local feedback service')
    assert deliver(out,transport=forbidden)['status']=='handled_by_hosted_broker'


def test_old_closures_are_not_uploaded(tmp_path):
    out=workspace(tmp_path)
    raw={'state':'ended','cycle_id':str(uuid.uuid4()),'feedback':{'status':'provided','reply':'Old local-only feedback'}}
    (out/'usage/lab-close.json').write_text(json.dumps(raw))
    assert deliver(out,transport=lambda *a:pytest.fail('no old feedback upload'))['status']=='not_submitted'


def test_conflict_is_terminal_without_losing_local_original(tmp_path):
    out=workspace(tmp_path);handle(out,'end lab');handle(out,'Fixture feedback')
    assert deliver(out,transport=lambda *a:(409,{'kind':'feedback_conflict'}))['status']=='rejected'
    assert read(out)['feedback']['reply']=='Fixture feedback'
    assert deliver(out,transport=lambda *a:pytest.fail('conflict replay'))['status']=='rejected'


def test_utf8_byte_cap_does_not_truncate_feedback_or_block_usage_report(tmp_path):
    out=workspace(tmp_path);handle(out,'end lab');text='雪'*3000;handle(out,text)
    assert status(out)['status']=='rejected'
    assert read(out)['feedback']['reply']==text
    assert Path(prepare(out)['debrief']).is_file()
