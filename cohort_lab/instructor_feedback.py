"""Optional, inference-free delivery of instructor feedback to the lab broker.

The installation credential can only append this installation's feedback. It
grants no model access or read access. No feedback text enters a model packet.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request
import uuid

URL='https://studio-north-bluechip-lab.blondeflour1.chatgpt.site/api/feedback/v1/submit'
NOTICE_VERSION=1
NOTICE="Your reply or skip will be saved for Professor Tian with your lab identifier (your UNC login in BlueChip). You may sign your reply if you would like to include your name."
MAX_BYTES=8000


def _read(path,default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    temporary.replace(path)


def _client():
    folder=Path.home()/'.studio-north-feedback'
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=folder/'client.json'
    if path.is_symlink():raise ValueError('feedback_credential_location')
    if not path.exists():
        value={'client_id':str(uuid.uuid4()),'secret':secrets.token_urlsafe(32),'scope':'feedback_append_only'}
        try:
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:pass
        else:
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:json.dump(value,stream)
    value=_read(path)
    if os.name!='nt' and path.stat().st_mode&0o077:raise ValueError('feedback_credential_permissions')
    if not isinstance(value,dict) or value.get('scope')!='feedback_append_only' or len(value.get('secret',''))!=43:
        raise ValueError('feedback_credential_invalid')
    uuid.UUID(value['client_id'])
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def _post(payload,client):
    request=urllib.request.Request(URL,data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8'),
        headers={'Content-Type':'application/json','User-Agent':'StudioNorth-Feedback/1.0',
                 'X-Lab-Feedback':client['client_id']+'.'+client['secret']},method='POST')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    try:
        with opener.open(request,timeout=5) as reply:
            data=reply.read(16385)
            if len(data)>16384:raise ValueError('feedback_response_too_large')
            return reply.status,json.loads(data)
    except urllib.error.HTTPError as error:
        try:body=json.loads(error.read(16384))
        except (ValueError,OSError):body={}
        return error.code,body


def _enqueue(output):
    output=Path(output)
    closing=_read(output/'usage/lab-close.json',{})
    session=_read(output/'usage/session.json',{})
    if session.get('route') not in {'personal','university_mcp'}:
        return None  # Hosted collection belongs to its authenticated broker.
    if closing.get('state')!='ended' or closing.get('notice_version')!=NOTICE_VERSION:
        return None  # Never retroactively upload a pre-notice closure.
    feedback=closing.get('feedback',{})
    if feedback.get('status') not in {'provided','declined'}:return None
    workspace=str(uuid.UUID(session['run_id']))
    text=feedback['reply'] if feedback['status']=='provided' else ''
    payload={'schema_version':1,'route':session['route'],'workspace_id':workspace,'close_id':closing['cycle_id'],
             'disposition':'submitted' if feedback['status']=='provided' else 'declined','reply':text,
             'reply_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'notice_version':NOTICE_VERSION,
             'closed_at':closing['ended_at'],'release':hashlib.sha256(json.dumps(
                 _read(output/'lesson_state.json',{}).get('implementation',{}),sort_keys=True).encode()).hexdigest()}
    path=output/'usage/instructor-feedback.json'
    outbox=_read(path,{'schema_version':1,'entries':[]})
    existing=next((e for e in outbox['entries'] if e['payload']['close_id']==payload['close_id']),None)
    if existing and existing['payload']!=payload:raise ValueError('feedback_local_conflict')
    if existing is None:
        outbox['entries'].append({'payload':payload,'status':'pending','attempts':0})
        _write(path,outbox)
    return outbox


def status(output):
    output=Path(output)
    closing=_read(output/'usage/lab-close.json',{})
    outbox=_read(output/'usage/instructor-feedback.json',{'entries':[]})
    current=next((e for e in outbox['entries'] if e['payload']['close_id']==closing.get('cycle_id')),None)
    if current is None:return {'status':'not_submitted'}
    result={'status':current['status'],'attempts':current['attempts']}
    if current.get('receipt'):result.update(current['receipt'])
    if current.get('last_error'):result['reason']=current['last_error']
    return result


def deliver(output, *, transport=None, client=None):
    """At most one bounded attempt per trigger; a persistent local outbox owns retries."""
    output=Path(output)
    session=_read(output/'usage/session.json',{})
    if session.get('route') not in {'personal','university_mcp'}:return {'status':'handled_by_hosted_broker'}
    outbox=_enqueue(output) or _read(output/'usage/instructor-feedback.json',{'entries':[]})
    entry=next((e for e in outbox['entries'] if e['status']=='pending'),None)
    if entry is None:return status(output)
    entry['attempts']+=1
    try:
        if len(entry['payload']['reply'].encode('utf-8'))>MAX_BYTES:
            entry.update(status='rejected',last_error='feedback_too_large')
        else:
            code,result=(transport or _post)(entry['payload'],client or _client())
            if code in {200,201} and result.get('ok') is True and isinstance(result.get('feedback_id'),str) and result.get('workspace_id')==entry['payload']['workspace_id'] and result.get('close_id')==entry['payload']['close_id']:
                entry.update(status='delivered',receipt={k:result[k] for k in ('feedback_id','participant_id','identity_kind','received_at')},delivered_at=time.time())
                entry.pop('last_error',None)
            elif code in {400,401,403,409,413,422}:
                entry.update(status='rejected',last_error='feedback_rejected_'+str(code))
            else:entry['last_error']='feedback_unavailable_'+str(code)
    except Exception:
        entry['last_error']='feedback_delivery_unavailable'
    _write(output/'usage/instructor-feedback.json',outbox)
    return status(output)


def deliver_safe(output):
    try:return deliver(output)
    except Exception:return {'status':'pending','reason':'feedback_delivery_unavailable'}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(deliver_safe(args.output)))
