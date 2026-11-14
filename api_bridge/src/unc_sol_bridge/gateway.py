"""Fixed UNC-pool gateway. Device authorization never exposes an APIM key to a harness."""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import fields

import httpx

from .client import MAX_RESPONSE_BYTES, Outcome
from .config import BridgeError

GATEWAY = "https://studio-north-bluechip-lab.blondeflour1.chatgpt.site/api/sol/v1"


class GatewayClient:
    def __init__(self, device_id, secret, *, transport=None):
        self.device_id, self._secret, self._transport = device_id, secret, transport

    async def _request(self, method, path, body=None):
        headers = {"X-Sol-Device": f"{self.device_id}.{self._secret}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(transport=self._transport, trust_env=False, follow_redirects=False,
                                         timeout=httpx.Timeout(170, connect=15)) as http:
                async with http.stream(method, GATEWAY + path, json=body, headers=headers) as reply:
                    raw = bytearray()
                    async for chunk in reply.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise BridgeError("gateway_response_invalid", "The gateway response exceeded its limit; preserve the reservation.")
                    data = json.loads(bytes(raw))
        except (httpx.HTTPError, ValueError):
            raise BridgeError("gateway_unavailable", "The gateway outcome is unavailable. Keep the reservation; retrieve this request ID instead of resubmitting it.") from None
        if not isinstance(data, dict):
            raise BridgeError("gateway_response_invalid", "The gateway did not return a structured result; preserve the reservation.")
        return data

    async def ask(self, instructions, text, request_id, intent):
        try:
            data = await self._request("POST", "/ask", {"request_id": request_id, "intent": intent,
                                                     "instructions": instructions, "packet": text})
        except BridgeError:
            return Outcome("gateway_unknown", detail="Retrieve the same request ID; do not send a new opening.")
        return self._outcome(data)

    async def recover(self, request_id):
        try:
            return self._outcome(await self._request("GET", "/requests/" + request_id))
        except BridgeError:
            return Outcome("gateway_unknown", detail="Recovery is unavailable; the reservation remains held.")

    def _outcome(self, data):
        if not data.get("ok") or not isinstance(data.get("outcome"), dict):
            known_unsent = data.get("provider_called") is False and data.get("charge") == "none"
            # A denied repeat may refer to an already-dispatched call. It is never proof of zero charge.
            if data.get("kind") in {"charge_held", "request_in_flight", "duplicate_request", "request_conflict"}:
                known_unsent = False
            detail = str(data.get("kind", "gateway_unknown"))[:80]
            canonical = data.get("request_id")
            import re
            if isinstance(canonical, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", canonical):
                detail += "; saved request: " + canonical
            return Outcome("gateway_denied" if known_unsent else "gateway_unknown", dispatched=not known_unsent, detail=detail)
        raw = data["outcome"]
        accepted = {f.name for f in fields(Outcome)}
        if set(raw) - accepted or not isinstance(raw.get("kind"), str):
            return Outcome("gateway_unknown", detail="invalid outcome shape")
        for name in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cached_input_tokens"):
            if raw.get(name) is not None and (type(raw[name]) is not int or raw[name] < 0):
                return Outcome("gateway_unknown", detail="invalid usage")
        return Outcome(**{**raw, "retrieved": bool(data.get("cached"))})


def new_secret():
    return secrets.token_urlsafe(32)


def secret_hash(secret):
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest()).decode().rstrip("=")


async def start_pair(secret, harness, *, transport=None):
    client = GatewayClient("pending", secret, transport=transport)
    data = await client._request("POST", "/pair/start", {"secret_hash": secret_hash(secret), "harness": harness})
    if not data.get("ok"):
        raise BridgeError("pairing_unavailable", "UNC connection setup is unavailable. No model was called.")
    return data
