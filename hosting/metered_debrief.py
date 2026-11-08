"""Instructor-owned, once-only metered review; no credential files or student keys.

The protected service bearer must already be in the process environment. The
caller persists dispatch intent before invoking this command, and never retries
an uncertain response. This is operator usage, separate from learner telemetry.
"""
import json
import os
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class MeteredClient:
    def __init__(self, timeout=900):
        self.timeout = timeout
        self.url=os.environ.get('STUDIO_NORTH_METERED_URL','http://127.0.0.1:8768/mcp')
        parsed=urlparse(self.url)
        if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}):
            raise ValueError('The instructor MCP requires TLS or a private loopback tunnel')
        self.headers = {'Authorization':'Bearer '+os.environ['BLUECHIP_METERED_SERVICE_TOKEN'],
                        'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
        self.sequence = 0
        self.rpc('initialize', {'protocolVersion':'2025-03-26', 'capabilities':{},
                               'clientInfo':{'name':'studio-north-debrief','version':'1'}})
        self.rpc('notifications/initialized', {}, notification=True)

    def rpc(self, method, params, notification=False):
        self.sequence += 1
        data={'jsonrpc':'2.0','method':method,'params':params}
        if not notification:
            data['id']=self.sequence
        request=Request(self.url,data=json.dumps(data).encode(),headers=self.headers)
        # No HTTP/provider retry: a lost response may have consumed a full call.
        with urlopen(request,timeout=self.timeout+45) as response:
            if response.headers.get('Mcp-Session-Id'):
                self.headers['Mcp-Session-Id']=response.headers['Mcp-Session-Id']
            raw=response.read(10_000_001).decode()
        if notification or not raw:
            return None
        if len(raw)>10_000_000:
            raise ValueError('Oversized MCP response')
        if raw.lstrip().startswith('{'):
            envelope=json.loads(raw)
        else:
            records=[json.loads(line[5:].strip()) for line in raw.splitlines() if line.startswith('data:')]
            envelope=next(x for x in reversed(records) if x.get('id')==self.sequence)
        if 'error' in envelope:
            raise RuntimeError('Metered MCP returned an error')
        return envelope.get('result')

    def tool(self, name, arguments):
        result=self.rpc('tools/call',{'name':name,'arguments':arguments})
        if result.get('structuredContent'):
            return result['structuredContent']
        return json.loads(next(x['text'] for x in result['content'] if x['type']=='text'))

    def ready(self):
        capacity=self.tool('get_bluechip_capacity',{})
        if not capacity.get('configured') or not capacity.get('model_policy_matches'):
            raise RuntimeError('Instructor debrief service is not ready')
        return capacity

    def review(self, packet, *, timeout=900):
        from hosting.student_debrief import RUBRIC
        return self.tool('ask_claude',{'prompt':RUBRIC+'\nFROZEN LEARNER EVIDENCE:\n'+json.dumps(packet,ensure_ascii=False),
                    'effort':'high','priority':'low','timeout_seconds':timeout,'workload':'automation'})


def checked_response(receipt):
    if (receipt.get('incomplete') is not False or receipt.get('stop_reason')!='end_turn'
        or receipt.get('error_code') or not receipt.get('model')
        or receipt.get('model')!=receipt.get('requested_model')
        or receipt.get('model_selection')!='server_default' or receipt.get('workload')!='automation'):
        raise ValueError('The metered review is not a verified complete response')
    text=receipt['text'].strip()
    if text.startswith('```json') and text.endswith('```'):
        text=text[7:-3].strip()
    return json.loads(text)
