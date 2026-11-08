import io
import json
from urllib.error import HTTPError

import pytest

from hosting import router_provider as provider


def fixture(monkeypatch):
    monkeypatch.setenv('FIXTURE_GPU_KEY','fixture')
    return ({'id':'gpu-1','base_url':'http://127.0.0.1:9999','api_key_env':'FIXTURE_GPU_KEY','model_alias':'fixture',
             'revision':'pin','manifest_hash':'manifest'},
            {'attempt_id':'fixture-attempt','payload':{'question':'Explain the checkpoint','evidence':{'step':1}}})


@pytest.mark.parametrize('count',[31000,-1,True])
def test_invalid_token_count_never_dispatches_generation(monkeypatch,count):
    spec,ticket=fixture(monkeypatch);calls=[]
    def request(req,**kw):
        calls.append(req.full_url)
        assert req.full_url.endswith('/tokenize')
        body=json.loads(req.data)
        assert body['add_generation_prompt'] and not body['add_special_tokens']
        assert body['chat_template_kwargs']=={'enable_thinking':False}
        return io.BytesIO(json.dumps({'count':count,'max_model_len':32768}).encode())
    monkeypatch.setattr(provider,'urlopen',request)
    result=provider.generate(spec,ticket)
    assert result['status']=='not_sent' and result['usage']['total_tokens']==0 and len(calls)==1


def test_missing_key_never_opens_transport(monkeypatch):
    spec,ticket=fixture(monkeypatch);monkeypatch.delenv('FIXTURE_GPU_KEY')
    monkeypatch.setattr(provider,'urlopen',lambda *a,**kw:pytest.fail('must not call network'))
    assert provider.generate(spec,ticket)['status']=='not_sent'


def test_http_rejection_is_settled_without_retry(monkeypatch):
    spec,ticket=fixture(monkeypatch);calls=[]
    def request(req,**kw):
        calls.append(req.full_url)
        if req.full_url.endswith('/tokenize'):return io.BytesIO(b'{"count":50,"max_model_len":32768}')
        raise HTTPError(req.full_url,503,'fixture',{},io.BytesIO(b'private provider error'))
    monkeypatch.setattr(provider,'urlopen',request)
    result=provider.generate(spec,ticket)
    assert result['status']=='http_rejected' and result['http_status']==503 and len(calls)==2
    assert 'private' not in json.dumps(result)


def test_post_dispatch_transport_failure_remains_ambiguous(monkeypatch):
    spec,ticket=fixture(monkeypatch)
    def request(req,**kw):
        if req.full_url.endswith('/tokenize'):return io.BytesIO(b'{"count":50,"max_model_len":32768}')
        raise TimeoutError('generation may still be running')
    monkeypatch.setattr(provider,'urlopen',request)
    with pytest.raises(TimeoutError):provider.generate(spec,ticket)
