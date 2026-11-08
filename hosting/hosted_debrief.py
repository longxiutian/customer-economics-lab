"""A separate debrief job consumes completed receipts; it never repeats analysis."""
import json
import hashlib
from pathlib import Path
import time

from cohort_lab.hosted import write_json, io_path
from hosting.telemetry import Telemetry
from hosting.student_debrief import freeze, provider_packet, validate_response, render


def input_hash(output):
    output=Path(output)
    hashes={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in
            ('report/customer-economics-report.pdf','learner_choices.json') if (output/name).is_file()}
    return hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()


def completed(output, *, expected_hash=None):
    root=io_path(output)/'personal-debrief'
    pointer=root/'completion.json'
    if pointer.is_file():
        saved=json.loads(pointer.read_text(encoding='utf-8'))
        if saved.get('input_hash')==(expected_hash or input_hash(output)) and all((root/name).is_file() and hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in saved.get('artifacts',{}).items()) and len(saved.get('artifacts',{}))==2:
            return saved
    return {'status':'pending','reason':'The report is ready; request the separate personal debrief.'}


def prepare(config, output, receipts, job):
    """CPU side: freeze redacted evidence after the final receipt was committed."""
    root=Path(output)/'personal-debrief'
    root.mkdir(parents=True,exist_ok=True)
    fingerprint=input_hash(output)
    version=root/fingerprint
    version.mkdir(parents=True,exist_ok=True)
    telemetry=config.get('telemetry')
    if not telemetry:
        raise ValueError('Instructor telemetry configuration is missing')
    ledger=Telemetry(telemetry['path'])
    for path in sorted(Path(receipts).glob('*.json')):
        receipt=json.loads(path.read_text(encoding='utf-8'))
        if receipt['payload']['action']!='debrief':
            ledger.ingest_receipt(receipt,session_id=telemetry['session_id'])
    snapshot=freeze(ledger,run_id=job['run_id'],session_id=telemetry['session_id'],path=version/'evidence.json',fixture=config.get('fixture',False))
    return {'binding':fingerprint,'evidence':provider_packet(snapshot)}


def create(config, output, receipts, job, *, client_factory=None):
    return create_frozen(config,output,prepare(config,output,receipts,job),job,client_factory=client_factory)


def create_frozen(config, output, frozen, job, *, client_factory=None):
    """Windows review side: accepts only the assigned broker job's frozen packet."""
    import re
    from hosting.metered_debrief import MeteredClient, checked_response
    fingerprint=frozen['binding']
    if not re.fullmatch('[a-f0-9]{64}',fingerprint):raise ValueError('Invalid report binding')
    root=io_path(output)/'personal-debrief';version=root/fingerprint
    version.mkdir(parents=True,exist_ok=True)
    snapshot=frozen['evidence']
    # The receipt is content-bound, not just file-path-bound, across reconnects.
    saved=version/'review-evidence.json'
    if saved.exists() and json.loads(saved.read_text(encoding='utf-8'))!=snapshot:
        raise ValueError('Frozen evidence changed for this report binding')
    write_json(saved,snapshot)
    ready=completed(output,expected_hash=fingerprint)
    if ready['status']=='completed':return ready
    attempt=version/'review-attempt.json'
    provider=version/'provider-receipt.json'
    if not provider.is_file():
        if attempt.exists():
            return {'status':'pending_operator_reconciliation','reason':'The original review may have been dispatched; it has not been repeated.'}
        if not config.get('debrief_enabled'):
            return {'status':'pending','reason':'The instructor review service has not been enabled.'}
        remaining=min(900,int(job.get('deadline',config['expires_at'])-time.time()-60))
        if remaining<60:
            return {'status':'pending','reason':'There is insufficient time left for a reviewed debrief.'}
        # Readiness is not a provider dispatch. A failure here can be retried safely.
        client=(client_factory or MeteredClient)(timeout=remaining)
        client.ready()
        write_json(attempt,{'state':'dispatch_possible','snapshot_id':snapshot['snapshot_id'],
                            'job_id':job['id'],'started_at':time.time()})
        receipt=client.review(provider_packet(snapshot),timeout=remaining)
        write_json(provider,receipt)
    if json.loads(attempt.read_text(encoding='utf-8'))['snapshot_id']!=snapshot['snapshot_id']:
        raise ValueError('Provider receipt belongs to a different frozen snapshot')
    receipt=json.loads(provider.read_text(encoding='utf-8'))
    response=checked_response(receipt)
    validate_response(snapshot,response)
    write_json(version/'validated-response.json',response)
    provenance={k:receipt.get(k) for k in ('model','requested_model','model_selection','stop_reason','usage')}
    provenance.update(effort='high',usage_scope='Instructor debrief generation; separate from learner usage')
    render(snapshot,response,path=root/'personal-debrief.html',provenance=provenance)
    from hosting.debrief_pdf import render_pdf
    render_pdf(snapshot,response,root/'personal-debrief.pdf',model=receipt['model'])
    write_json(root/'completion.json',{'status':'completed','snapshot_id':snapshot['snapshot_id'],'review_model':receipt['model'],
        'source':'Reviewed frozen learner evidence','completed_at':time.time(),'input_hash':fingerprint,
        'artifacts':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('personal-debrief.html','personal-debrief.pdf')},
        'usage_coverage':snapshot['coverage']})
    return completed(output,expected_hash=fingerprint)


def execute_assigned(config, job, *, client_factory=None):
    """Review lane on Windows; no remote workspace mount or analysis execution."""
    import copy
    from cohort_lab.hosted import HostedLesson, digest, IDENTIFIER
    if not IDENTIFIER.fullmatch(job['id']) or job['release_hash']!=config['release_hash']:
        raise ValueError('Invalid assigned job or pinned release')
    source=job.get('source_packet') or {}
    if job['payload']['action']!='debrief' or source.get('step')!=18 or not source.get('validation',{}).get('report_complete'):
        raise ValueError('A debrief needs this assigned workspace\'s validated report')
    frozen=source.get('debrief_input')
    if not frozen:raise ValueError('The CPU worker has not frozen review evidence')
    adapter=HostedLesson(Path(config['runtime']))
    base,output,receipts=adapter.locations(job['run_id'])
    output,receipts=io_path(output),io_path(receipts)
    receipt_path=receipts/(job['id']+'.json')
    request_hash=digest({'payload':job['payload'],'source':frozen,'release_hash':job['release_hash']})
    with adapter.lock(base):
        if receipt_path.is_file():
            prior=json.loads(receipt_path.read_text(encoding='utf-8'))
            if prior['request_hash']!=request_hash:raise ValueError('Conflicting debrief replay')
            if prior.get('status')=='completed':return prior['result']
        write_json(receipt_path,{'status':'started','request_hash':request_hash,'job_id':job['id']})
        packet=copy.deepcopy(source)
        try:packet['personal_debrief']=create_frozen(config,output,frozen,job,client_factory=client_factory)
        except Exception as exc:
            packet['personal_debrief']={'status':'pending_operator_review','error_type':type(exc).__name__,
                                       'reason':'Your main report is saved. The personal review requires an instructor check.'}
        done=packet['personal_debrief']['status']=='completed'
        if done:
            for name in ('personal-debrief.html','personal-debrief.pdf'):
                path=output/'personal-debrief'/name;data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
                label='personal-debrief/'+name
                packet['artifacts'].append({'artifact_id':hashlib.sha256((label+sha).encode()).hexdigest(),
                    'name':label,'sha256':sha,'size':len(data),'mime':'application/pdf' if name.endswith('.pdf') else 'text/html',
                    'local_path':str(path)})
        packet['validation']['checks']['personal_debrief']=done
        packet['validation']['workflow_complete']=bool(packet['validation']['report_complete'] and done)
        result={'api_version':'studio-north-bluechip/1','run_id':job['run_id'],'job_id':job['id'],
                'release_hash':job['release_hash'],'packet':packet,'execution':{'fresh_fit':False},'finished_at':time.time()}
        write_json(receipt_path,{'status':'completed','request_hash':request_hash,'job_id':job['id'],'result':result})
        return result
