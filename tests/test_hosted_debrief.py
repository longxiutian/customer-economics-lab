import json
import time
from pathlib import Path

import pytest
from pypdf import PdfReader

from hosting.hosted_debrief import create, completed
from hosting.student_debrief import RUBRIC_VERSION
from hosting.telemetry import Telemetry


def fixture(tmp_path):
    output=tmp_path/'lesson';(output/'report').mkdir(parents=True)
    (output/'report/customer-economics-report.pdf').write_bytes(b'fixture-report')
    (output/'learner_choices.json').write_text('{"final_verdict":"Investigate cohort quality"}')
    receipts=tmp_path/'receipts';receipts.mkdir()
    config={'telemetry':{'path':str(tmp_path/'events.sqlite'),'session_id':'session'},'fixture':True,'debrief_enabled':True,'expires_at':time.time()+7200}
    Telemetry(config['telemetry']['path']).append(event_id='question',run_id='run-0001',session_id='session',kind='lab_request',happened_at=1,
        payload={'action':'message','message':'How does iCAC inform an acquisition decision without changing LTV?','source':'lab_api_received','checkpoint_before':12})
    return output,receipts,config,{'id':'debrief-job-001','run_id':'run-0001','deadline':time.time()+7200}


class Reviewer:
    calls=0
    def __init__(self,**kw):pass
    def ready(self):return {'configured':True}
    def review(self,packet,**kw):
        type(self).calls+=1
        source=next(x for x in packet['evidence'] if x['kind']=='prompt_excerpt')
        row={'text':'You asked how incremental acquisition cost informs a decision about customer value.','evidence_ids':[source['id']],'quote':source['text']}
        next_step={'text':'Compare channel decisions using incremental contribution and acquisition cost.','evidence_ids':[source['id']],'prompt':'Show how the channel decision changes across plausible iCAC estimates.'}
        response={'rubric_version':RUBRIC_VERSION,'snapshot_id':packet['snapshot_id'],'observations':[row,row],
                  'studio_north_next_steps':[next_step,next_step],'ai_learning_next_steps':[next_step,next_step]}
        return {'text':json.dumps(response),'model':'fixture-reviewer','requested_model':'fixture-reviewer','model_selection':'server_default',
                'incomplete':False,'stop_reason':'end_turn','workload':'automation','usage':{'input_tokens':200,'output_tokens':150}}


def test_review_is_personal_private_validated_and_idempotent(tmp_path):
    output,receipts,config,job=fixture(tmp_path)
    Reviewer.calls=0
    result=create(config,output,receipts,job,client_factory=Reviewer)
    assert result['status']=='completed' and Reviewer.calls==1
    pdf=output/'personal-debrief/personal-debrief.pdf'
    text='\n'.join(p.extract_text() for p in PdfReader(pdf).pages)
    assert 'iCAC' in text and 'fixture-reviewer' in text and 'Native BlueChip' in text
    assert result==create(config,output,receipts,job,client_factory=Reviewer) and Reviewer.calls==1
    assert not any(e['kind']=='usage' for e in Telemetry(config['telemetry']['path']).events('run-0001','session'))
    (output/'learner_choices.json').write_text('{"final_verdict":"A changed judgment"}')
    assert completed(output)['status']=='pending'
    create(config,output,receipts,job,client_factory=Reviewer)
    assert Reviewer.calls==2


def test_uncertain_review_never_replays_or_changes_report(tmp_path):
    output,receipts,config,job=fixture(tmp_path)
    class Lost(Reviewer):
        def review(self,*a,**kw):
            type(self).calls+=1;raise TimeoutError('after possible dispatch')
    Lost.calls=0
    with pytest.raises(TimeoutError):create(config,output,receipts,job,client_factory=Lost)
    pending=create(config,output,receipts,{**job,'id':'another-job'},client_factory=Lost)
    assert pending['status']=='pending_operator_reconciliation' and Lost.calls==1
    assert (output/'report/customer-economics-report.pdf').read_bytes()==b'fixture-report'
    assert completed(output)['status']=='pending'


def test_foreign_evidence_and_incomplete_review_not_published(tmp_path):
    output,receipts,config,job=fixture(tmp_path)
    class Wrong(Reviewer):
        def review(self,*a,**kw):
            result=super().review(*a,**kw)
            data=json.loads(result['text']);data['observations'][0]['evidence_ids']=['other-student']
            result['text']=json.dumps(data);return result
    with pytest.raises(ValueError):create(config,output,receipts,job,client_factory=Wrong)
    assert not (output/'personal-debrief/completion.json').exists()
    assert not (output/'personal-debrief/personal-debrief.pdf').exists()


def test_frozen_review_and_remote_job_preserve_report_without_refitting(tmp_path):
    from hosting.hosted_debrief import prepare,execute_assigned,create_frozen
    from cohort_lab.hosted import HostedLesson
    output,receipts,config,job=fixture(tmp_path)
    frozen=prepare(config,output,receipts,job)
    assert 'private_scope' not in frozen['evidence']
    source={'step':18,'artifacts':[{'artifact_id':'main-report','name':'report/customer-economics-report.pdf'}],
            'debrief_input':frozen,'validation':{'report_complete':True,'workflow_complete':False,'checks':{}}}
    config.update(runtime=str(tmp_path/'windows-review'),release_hash='release')
    job.update(release_hash='release',payload={'action':'debrief'},source_packet=source)
    Reviewer.calls=0
    result=execute_assigned(config,job,client_factory=Reviewer)
    assert result['packet']['validation']['workflow_complete'] and not result['execution']['fresh_fit']
    assert result['packet']['artifacts'][0]==source['artifacts'][0] and len(result['packet']['artifacts'])==3
    assert result==execute_assigned(config,job,client_factory=Reviewer) and Reviewer.calls==1
    assert source['validation']['workflow_complete'] is False
    _,review_output,_=HostedLesson(tmp_path/'windows-review').locations(job['run_id'])
    altered=json.loads(json.dumps(frozen));altered['evidence']['snapshot_id']='another-snapshot'
    with pytest.raises(ValueError,match='Frozen evidence changed'):
        create_frozen(config,review_output,altered,job,client_factory=Reviewer)
