"""Explicit learner-controlled closing; feedback remains in the learner's workspace."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time
import uuid

TRIGGERS = frozenset({'end lab', 'end simulation'})
QUESTION = 'Any feedback to Professor Tian?'
SKIPS = frozenset({'skip', 'skip feedback', 'no feedback', 'no', 'none', 'prefer not to answer'})


def read(output):
    path = Path(output)/'usage/lab-close.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'state':'active'}


def _write(output, value):
    path=Path(output)/'usage/lab-close.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    temporary.replace(path)


def artifacts(output):
    return {name:hashlib.sha256((Path(output)/name).read_bytes()).hexdigest() if (Path(output)/name).is_file() else None
            for name in ('report/customer-economics-report.pdf','learner_choices.json')}


def summary(output):
    value=read(output)
    result={k:value[k] for k in ('state','cycle_id','trigger','requested_at','ended_at','cutoff','artifacts_at_end') if k in value}
    result['usage_report_allowed']=value.get('state')=='ended' and value.get('feedback',{}).get('status') in {'provided','declined'}
    if value['state']=='awaiting_feedback':result['question']=QUESTION
    if value.get('feedback'):result['feedback']={'status':value['feedback']['status'],'sha256':value['feedback']['sha256'],'storage':'workspace_only','sent_to_professor':False}
    return result


def handle(output, message):
    """Consume only end/feedback/resume controls. Never advances analysis or sends data."""
    if not isinstance(message,str):raise ValueError('Use the learner\'s actual message.')
    normalized=message.strip().casefold().rstrip('.!?').strip()
    value=read(output)
    if normalized=='continue lab' and value['state']!='active':
        history=value.get('history',[])+[{k:v for k,v in value.items() if k!='history'}]
        _write(output,{'state':'active','history':history})
        return True
    if normalized in TRIGGERS:
        if value['state']=='active':
            stamp=time.time()
            value={**value,'schema_version':1,'state':'awaiting_feedback','cycle_id':str(uuid.uuid4()),
                   'trigger':message,'requested_at':stamp,'cutoff':stamp,'artifacts_at_end':artifacts(output),'question':QUESTION}
            _write(output,value)
        return True
    if value['state']=='awaiting_feedback':
        if not normalized or normalized=='next step':return True
        value.update(state='ended',ended_at=time.time(),feedback={
            'status':'declined' if normalized in SKIPS else 'provided',
            'reply':message,'sha256':hashlib.sha256(message.encode('utf-8')).hexdigest(),
            'storage':'workspace_only','sent_to_professor':False})
        _write(output,value)
        return True
    return value['state']=='ended'


def require_ended(output, *, verify_artifacts=False):
    value=read(output)
    if value.get('state')!='ended' or value.get('trigger','').strip().casefold().rstrip('.!?').strip() not in TRIGGERS or value.get('feedback',{}).get('status') not in {'provided','declined'}:
        raise ValueError('Usage report is locked. The learner must say end lab or end simulation, then answer or skip: '+QUESTION)
    if verify_artifacts and value.get('artifacts_at_end')!=artifacts(output):
        raise ValueError('The report or judgments changed after ending. Type continue lab, then end the session again.')
    return summary(output)


def binding(output):
    """A redacted, stable close receipt; instructor-feedback text is never review evidence."""
    value=require_ended(output)
    wire=json.dumps(value,sort_keys=True,separators=(',',':'))
    return {**value,'sha256':hashlib.sha256(wire.encode()).hexdigest()}
