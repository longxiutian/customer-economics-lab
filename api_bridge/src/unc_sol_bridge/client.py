"""One fixed, non-streaming Responses call to UNC gpt-6.1-sol. No retries, redirects, proxies or overrides."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx

from .config import EFFORT, MAX_OUTPUT_TOKENS, MODEL

# The UNC Responses endpoint verified in the existing instructor integration.
# Never read from client configuration, environment variables or MCP arguments.
RESPONSES_URL = "https://azureaiapi.cloud.unc.edu/openai/v1/responses"
SNAPSHOT = re.compile(r"gpt-6\.1-sol(-\d{4}-\d{2}-\d{2})?")  # the alias or a dated snapshot of the same model
MAX_RESPONSE_BYTES = 262_144
TOTAL_SECONDS = 150.0


@dataclass(frozen=True)
class Outcome:
    kind: str
    dispatched: bool = True
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    model: str = ""
    response_id: str = ""
    http_status: int | None = None
    detail: str = ""


def endpoint_ready(url=None) -> bool:
    return (RESPONSES_URL if url is None else url).startswith("https://")


def build_request(instructions: str, text: str) -> dict:
    return {"model": MODEL, "instructions": instructions, "input": text, "max_output_tokens": MAX_OUTPUT_TOKENS,
            "reasoning": {"effort": EFFORT}, "store": False, "stream": False}


def redact(value, key: str = "") -> str:
    text = str(value).replace(key, "_") if key else str(value)
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", text)[:80]


class SolClient:
    def __init__(self, api_key: str, *, transport=None, url=None):
        self._key, self._transport = api_key, transport
        self._url = RESPONSES_URL if url is None else url

    async def ask(self, instructions: str, text: str) -> Outcome:
        body = json.dumps(build_request(instructions, text)).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json", "Accept": "application/json"}
        try:
            async with asyncio.timeout(TOTAL_SECONDS):
                async with httpx.AsyncClient(transport=self._transport, trust_env=False, follow_redirects=False,
                                             timeout=httpx.Timeout(120.0, connect=15.0)) as http:
                    async with http.stream("POST", self._url, content=body, headers=headers) as response:
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > MAX_RESPONSE_BYTES:
                                return Outcome("response_too_large", http_status=response.status_code)
                        status = response.status_code
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:  # no request bytes left this machine
            return Outcome("not_dispatched", dispatched=False, detail=type(error).__name__)
        except (httpx.TimeoutException, TimeoutError) as error:  # sent; the bill is unknown
            return Outcome("timeout", detail=type(error).__name__)
        except httpx.HTTPError as error:
            return Outcome("transport_error", detail=type(error).__name__)
        return self._parse(status, bytes(raw))

    def _parse(self, status: int, raw: bytes) -> Outcome:
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            data = None
        data = data if isinstance(data, dict) else {}
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        counts = [usage.get(name) for name in ("input_tokens", "output_tokens", "total_tokens")]
        known = all(type(count) is int and count >= 0 for count in counts[:2])
        def subset(container, name):
            details = usage.get(container)
            value = details.get(name) if isinstance(details, dict) else None
            return value if type(value) is int and value >= 0 else None
        model = data.get("model") if isinstance(data.get("model"), str) else ""
        facts = {"http_status": status, "model": redact(model, self._key), "response_id": redact(data.get("id", ""), self._key),
                 "input_tokens": counts[0] if known else None, "output_tokens": counts[1] if known else None,
                 "total_tokens": counts[2] if known and type(counts[2]) is int and counts[2] >= 0 else None,
                 "reasoning_tokens": subset("output_tokens_details", "reasoning_tokens"),
                 "cached_input_tokens": subset("input_tokens_details", "cached_tokens")}
        if status != 200:
            kind = ("redirect_refused" if 300 <= status < 400 else "auth_rejected" if status in (401, 403)
                    else "quota_rejected" if status == 429 else "upstream_error")
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            code = error.get("code") or error.get("type")
            return Outcome(kind, detail=redact(code, self._key) if isinstance(code, str) else "", **facts)
        if not data:
            return Outcome("invalid_response", detail="body is not a JSON object", **facts)
        if not SNAPSHOT.fullmatch(model):
            return Outcome("model_mismatch", detail="served model is not the pinned Sol model", **facts)
        if not known:
            return Outcome("usage_missing", **facts)
        texts, refusals = [], []
        for item in data.get("output") if isinstance(data.get("output"), list) else []:
            parts = item.get("content") if isinstance(item, dict) and item.get("type") == "message" else None
            for part in parts if isinstance(parts, list) else []:
                if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
                elif isinstance(part, dict) and part.get("type") == "refusal":
                    refusals.append(str(part.get("refusal", ""))[:500])
        text = "".join(texts).replace(self._key, "_")
        if data.get("status") == "incomplete":
            details = data.get("incomplete_details") if isinstance(data.get("incomplete_details"), dict) else {}
            return Outcome("incomplete", text=text, detail=redact(details.get("reason", ""), self._key), **facts)
        if data.get("status") != "completed":
            return Outcome("invalid_response", detail="status is not completed", **facts)
        if refusals:
            return Outcome("refused", text=" ".join(refusals).replace(self._key, "_"), **facts)
        return Outcome("completed" if text.strip() else "empty_output", text=text, **facts)
