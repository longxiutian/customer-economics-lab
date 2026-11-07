"""Private bounded provider child. Credentials are read only from an env variable.

Run by nemotron_router, never exposed as a student tool. Registry/tunnel endpoints
and model-manifest attestations are maintained by the authorized Longleaf owner.
"""
import json
import os
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def generate(spec, ticket):
    base = spec["base_url"].rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("Provider transport must use TLS or an operator-owned loopback tunnel")
    token = os.environ[spec["api_key_env"]]
    payload = ticket["payload"]
    evidence = json.dumps(payload["evidence"], ensure_ascii=False)
    question = str(payload.get("question", "Explain this checkpoint."))
    if len(evidence) > 65000 or len(question) > 12000:
        raise ValueError("Interpretation exceeds the bounded evidence budget")
    from hosting.nemotron_interpret import SYSTEM_PROMPT
    body = {"model": spec["model_alias"], "messages": [{"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "CURRENT CHECKPOINT EVIDENCE:\n" + evidence + "\nLEARNER MESSAGE:\n" + question}],
        "max_tokens": 900, "temperature": 0.2, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False}}
    request = Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    started = time.time()
    with urlopen(request, timeout=75) as response:
        data = response.read(3_000_001)
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
            "started_at": started, "finished_at": time.time(), "latency_kind": "nonstreaming_response_elapsed"}


if __name__ == "__main__":
    incoming = json.load(sys.stdin)
    try:
        print(json.dumps(generate(incoming["replica"], incoming["ticket"]), ensure_ascii=False))
    except Exception as exc:
        # Parent treats a nonzero child as an uncertain dispatch, never an automatic retry.
        print(json.dumps({"error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
