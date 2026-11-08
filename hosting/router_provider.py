"""Private bounded provider child. Credentials are read only from an env variable.

Run by nemotron_router, never exposed as a student tool. Registry/tunnel endpoints
and model-manifest attestations are maintained by the authorized Longleaf owner.
"""
import hashlib
import json
import os
import sys
import time
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def prepare(spec, ticket):
    base = spec["base_url"].rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("Provider transport must use TLS or an operator-owned loopback tunnel")
    token = os.environ[spec["api_key_env"]]
    payload = ticket["payload"]
    from hosting.nemotron_interpret import SYSTEM_PROMPT, encode_evidence
    evidence = encode_evidence(payload["evidence"])
    question = str(payload.get("question", "Explain this checkpoint."))
    if len(evidence) > 65000 or len(question) > 12000:
        raise ValueError("Interpretation exceeds the bounded evidence budget")
    body = {"model": spec["model_alias"], "messages": [{"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "CURRENT CHECKPOINT EVIDENCE:\n" + evidence + "\nLEARNER MESSAGE:\n" + question}],
        "max_tokens": 1800, "temperature": 0.2, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False}}
    request = Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    return request


def generate(spec, ticket):
    try:
        request=prepare(spec,ticket)
        body=json.loads(request.data)
        token_body={k:body[k] for k in ('model','messages','chat_template_kwargs')}
        token_body.update(add_generation_prompt=True,add_special_tokens=False,return_token_strs=False)
        token_request=Request(spec['base_url'].rstrip('/')+'/tokenize',data=json.dumps(token_body).encode(),
                              headers=dict(request.header_items()))
        # vLLM /tokenize is reached through the operator's private loopback SSH
        # transport; unlike /v1 it is not claimed to enforce the API bearer.
        with urlopen(token_request,timeout=15) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('Oversized tokenizer response')
        counted=json.loads(raw)
        if type(counted.get('count')) is not int or counted['count']<0 or counted.get('max_model_len')!=32768 or counted['count']+1800>32768:
            raise ValueError('The templated request exceeds the pinned context budget')
    except Exception as exc:
        # No generation was dispatched. The private tokenizer may have been
        # called, but these failures cannot occupy an inference slot.
        return {'status':'not_sent','provider_attempted':False,'error_type':type(exc).__name__,
                'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'usage_source':'no_provider_dispatch'}
    started = time.time()
    try:
        with urlopen(request, timeout=110) as response:
            data = response.read(3_000_001)
    except HTTPError as exc:
        # A complete HTTP rejection is a settled request, never an automatic
        # generation retry. Retain no exception body (it may include private data).
        return {'status':'http_rejected','http_status':exc.code,'provider_attempted':True,
                'usage':None,'model':spec['model_alias'],'started_at':started,'finished_at':time.time()}
    if len(data) > 3_000_000:
        raise ValueError("Oversized provider response")
    response = json.loads(data)
    choice = (response.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    success = choice.get("finish_reason") == "stop" and bool(text.strip()) and response.get("model") == spec["model_alias"]
    return {"status": "completed" if success else "invalid_completion", "text": text,
            "finish_reason": choice.get("finish_reason"), "model": response.get("model"),
            "response_id": response.get("id"), "system_fingerprint": response.get("system_fingerprint"),
            "usage": response.get("usage"), "revision": spec["revision"], "replica_id": spec["id"],
            "manifest_hash": spec["manifest_hash"], "router_attempt_id": ticket["attempt_id"],
            "preflight_prompt_tokens":counted['count'],
            "provider_prompt_sha256": hashlib.sha256(json.dumps(body['messages'], ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            "started_at": started, "finished_at": time.time(), "latency_kind": "nonstreaming_response_elapsed"}


if __name__ == "__main__":
    incoming = json.load(sys.stdin)
    try:
        print(json.dumps(generate(incoming["replica"], incoming["ticket"]), ensure_ascii=False))
    except Exception as exc:
        # Parent treats a nonzero child as an uncertain dispatch, never an automatic retry.
        print(json.dumps({"error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
