"""Local startup bookkeeping. It never contacts a model or changes a native provider."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .bridge import Bridge
from .config import BridgeError, load_config, MANAGED_ALLOCATION_LIMIT
from .credentials import _keyring, check_key
from .packets import source_fingerprint

RECORD_FIELDS = {"subscription", "period_id", "baseline_tokens", "baseline_source", "primary_key"}


def credential_record(path, source_root, run_dir):
    path = Path(path).resolve()
    if path.is_relative_to(source_root) or path.is_relative_to(run_dir):
        raise BridgeError("credential_location", "Keep the private credential file outside the checkout and its outputs.")
    try:
        if path.stat().st_size > 4096:
            raise ValueError
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise BridgeError("credential_file_invalid", "Use one private UNC credential record, not the class key pool. Do not open or print this file in chat; obtain a corrected private record.") from None
    if not isinstance(raw, dict) or set(raw) != RECORD_FIELDS:
        missing = sorted(RECORD_FIELDS - raw.keys()) if isinstance(raw, dict) else sorted(RECORD_FIELDS)
        extra_count = len(raw.keys() - RECORD_FIELDS) if isinstance(raw, dict) else 0
        raise BridgeError("credential_file_invalid",
                          f"Private record missing known fields: {missing}; unsupported field count: {extra_count}. "
                          "Do not open or print this file in chat; obtain a corrected private record.")
    key = check_key(raw["primary_key"])
    return {name: raw[name] for name in RECORD_FIELDS - {"primary_key"}}, key


def _local(root, args):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    completed = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                               encoding="utf-8", timeout=120, **options)
    if completed.returncode:
        # No arbitrary subprocess output enters the chat. The named local command can be diagnosed separately.
        raise BridgeError("local_setup_failed", "The local guided-workspace command failed; no model was called.",
                          command=args[0], exit_code=completed.returncode)


def prepare(*, config_path, source_root, run_dir, credential_file, harness):
    root, run, path = (Path(value).resolve() for value in (source_root, run_dir, config_path))
    if path.exists():
        config = load_config(path)
        if config.source_root != root or config.run_dir != run:
            raise BridgeError("config_conflict", "The existing configuration names a different checkout or workspace.")
        return Bridge(config).status()
    if path.is_relative_to(root) or path.is_relative_to(run):
        raise BridgeError("config_location", "Keep the owner-local bridge configuration outside the public checkout.")
    metadata, key = credential_record(credential_file, root, run)
    reference = {"kind": "keyring", "service": "unc-sol-bridge", "name": metadata["subscription"]}
    raw = {
        "schema_version": 1, "source_root": str(root), "run_dir": str(run),
        "state_dir": str(Path.home() / ".unc-sol-bridge" / "state"),
        "subscription_label": metadata["subscription"], "period_id": metadata["period_id"],
        "baseline_tokens": metadata["baseline_tokens"], "baseline_source": metadata["baseline_source"],
        "allocation_cap": 400000, "phase": "startup", "stage_cap": 10000,
        "source_fingerprint": source_fingerprint(root), "credential_ref": reference,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Validate the complete configuration before saving a credential or starting the lesson.
    candidate = path.with_suffix(".candidate.json")
    try:
        candidate.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        config = load_config(candidate)
    finally:
        candidate.unlink(missing_ok=True)
    _keyring().set_password(reference["service"], reference["name"], key)
    _local(root, ["student.py", "--output", str(run), "start"])
    _local(root, ["-m", "cohort_lab.debrief", "--output", str(run), "init",
                  "--route", "university_mcp", "--harness", harness])
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    config = load_config(path)
    return Bridge(config).status()


async def connect(*, config_path, source_root, run_dir, harness, transport=None):
    """UNC device pairing. This calls the gateway, never a model or the APIM key service."""
    from .gateway import GatewayClient, new_secret, start_pair
    from .credentials import load_key
    import time
    root, run, path = (Path(value).resolve() for value in (source_root, run_dir, config_path))
    if path.exists():
        config = load_config(path)
        if config.mode != "gateway" or config.source_root != root or config.run_dir != run:
            raise BridgeError("config_conflict", "The existing configuration belongs to a different route or workspace.")
        client = GatewayClient(config.device_id, load_key(config.credential_ref), transport=transport)
        status = await client._request("POST", "/pair/poll", {})
        if status.get("status") == "approved":
            return {**Bridge(config).status(), "connection": "approved"}
        if status.get("status") not in {"pending", "expired"}:
            raise BridgeError("pairing_unavailable", "This device authorization is unavailable. No model was called.")
        pairing_path = path.with_suffix(".pairing.json")
        try:
            pairing = json.loads(pairing_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pairing = {}
        if status["status"] == "expired" or not pairing.get("user_code"):
            pairing = await client._request("POST", "/pair/renew", {})
            if not pairing.get("ok") or not pairing.get("user_code"):
                raise BridgeError("pairing_unavailable", "A new pairing code was not issued. No model was called.")
            pairing_path.write_text(json.dumps(pairing, indent=2)+"\n", encoding="utf-8")
        return {**Bridge(config).status(), "pairing": pairing,
                "next": "Open approval_url, send pair USER_CODE, return here and say done."}
    if path.is_relative_to(root) or path.is_relative_to(run):
        raise BridgeError("config_location", "Keep device configuration outside the repository and run folder.")
    if harness not in {"Codex", "Claude Code", "VS Code"}:
        raise BridgeError("invalid_arguments", "Use Codex, Claude Code or VS Code for the harness label.")
    keyring = _keyring()  # fail before creating a remote pending device if secure storage is unavailable
    secret = new_secret()
    pairing = await start_pair(secret, harness, transport=transport)
    reference = {"kind": "keyring", "service": "unc-sol-device", "name": pairing["device_id"]}
    raw = {"schema_version": 2, "mode": "gateway", "device_id": pairing["device_id"],
           "source_root": str(root), "run_dir": str(run), "state_dir": str(Path.home()/".unc-sol-bridge"/"state"),
           "subscription_label": "managed-" + pairing["device_id"][:20], "period_id": time.strftime("%Y-%m", time.gmtime()),
           "baseline_tokens": 0, "baseline_source": "Gateway centrally accounts for all assigned UNC subscriptions.",
           "allocation_cap": MANAGED_ALLOCATION_LIMIT, "phase": "startup", "stage_cap": 10000,
           "source_fingerprint": source_fingerprint(root), "credential_ref": reference}
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(".candidate.json")
    try:
        candidate.write_text(json.dumps(raw, indent=2)+"\n", encoding="utf-8")
        load_config(candidate)
    finally:
        candidate.unlink(missing_ok=True)
    keyring.set_password(reference["service"], reference["name"], secret)
    _local(root, ["student.py", "--output", str(run), "start"])
    _local(root, ["-m", "cohort_lab.debrief", "--output", str(run), "init", "--route", "university_mcp", "--harness", harness])
    path.write_text(json.dumps(raw, indent=2)+"\n", encoding="utf-8")
    # Pair code is not a credential. Preserve it for resuming setup after a local interruption.
    pairing_path = path.with_suffix(".pairing.json")
    pairing_path.write_text(json.dumps(pairing, indent=2)+"\n", encoding="utf-8")
    return {**Bridge(load_config(path)).status(), "pairing": pairing,
            "next": "Open approval_url, send pair USER_CODE, then return to this chat and say done. Never paste a key."}
