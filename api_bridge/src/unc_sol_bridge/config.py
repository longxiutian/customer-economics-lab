"""Owner-local bridge configuration: paths, one allocation and a phase. Never a secret, endpoint or model."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

MODEL = "gpt-6.1-sol"
EFFORT = "medium"
MAX_OUTPUT_TOKENS = 3000  # visible output plus reasoning
PROJECT_OUTPUT_TOKENS = 6000  # code needs more space; still reserved fully before each dispatch


def output_limit(intent):
    return PROJECT_OUTPUT_TOKENS if intent == "project" else MAX_OUTPUT_TOKENS


ALLOCATION_LIMIT = 400_000
MANAGED_ALLOCATION_LIMIT = 127 * ALLOCATION_LIMIT  # local ceiling only; central admission owns the actual pool
PHASES = {"startup": (10_000, 5_000), "pilot": (100_000, 16_000), "full": (ALLOCATION_LIMIT, 16_000)}  # stage cap, packet bytes
MANAGED_PHASES = {**PHASES, "full": (MANAGED_ALLOCATION_LIMIT, 16_000)}
RELEASE_PHASES = frozenset({"startup", "full"})
REQUIRED = {"schema_version", "source_root", "run_dir", "state_dir", "subscription_label", "period_id", "baseline_tokens",
            "baseline_source", "allocation_cap", "phase", "stage_cap", "source_fingerprint", "credential_ref"}
OPTIONAL = {"data_dir", "packet_max_bytes", "project_only"}
GATEWAY_FIELDS = {"mode", "device_id"}
KEY_SHAPED = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}|(?i:bearer)\s+\S{8,}|\beyJ[A-Za-z0-9_-]{8,}|(?<![A-Fa-f0-9])[A-Fa-f0-9]{32}(?![A-Fa-f0-9])")
SECRETISH = re.compile(KEY_SHAPED.pattern + r"|[A-Za-z0-9+/_=-]{48,}")


class BridgeError(Exception):
    """A typed failure that is safe to show in the host chat and never carries secret material."""

    def __init__(self, kind: str, message: str, **facts):
        super().__init__(message)
        self.kind, self.message, self.facts = kind, message, facts


@dataclass(frozen=True)
class BridgeConfig:
    path: Path
    source_root: Path
    data_dir: Path
    run_dir: Path
    state_dir: Path
    subscription_label: str
    period_id: str
    baseline_tokens: int
    baseline_source: str
    allocation_cap: int
    phase: str
    stage_cap: int
    packet_max_bytes: int
    source_fingerprint: str
    credential_ref: dict
    mode: str = "direct"
    device_id: str = ""
    project_only: bool = False


def _text(raw, key, pattern, limit=64):
    value = raw.get(key)
    if not isinstance(value, str) or len(value) > limit or not re.fullmatch(pattern, value) or SECRETISH.search(value):
        raise BridgeError("config_invalid", f"{key} is missing, malformed or shaped like secret material.")
    return value


def _integer(raw, key, low, high):
    value = raw.get(key)
    if type(value) is not int or not low <= value <= high:
        raise BridgeError("config_invalid", f"{key} must be an integer from {low} to {high}.")
    return value


def _directory(raw, key):
    value = raw.get(key)
    if not isinstance(value, str) or "\0" in value or KEY_SHAPED.search(value) or not Path(value).is_absolute():
        raise BridgeError("config_invalid", f"{key} must be an absolute local path.")
    path = Path(value).resolve()
    if path == Path(path.anchor):
        raise BridgeError("config_invalid", f"{key} may not be a filesystem root.")
    return path


def load_config(path) -> BridgeConfig:
    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BridgeError("config_invalid", f"The configuration file is unreadable ({type(error).__name__}).") from None
    required = REQUIRED | GATEWAY_FIELDS if isinstance(raw, dict) and raw.get("schema_version") == 2 else REQUIRED
    if not isinstance(raw, dict) or (set(raw) ^ required) - OPTIONAL:
        wrong = sorted(str(key)[:32] for key in (set(raw) ^ required) - OPTIONAL)[:8] if isinstance(raw, dict) else []
        raise BridgeError("config_invalid", f"Missing or unsupported configuration keys: {wrong}. "
                          "Endpoint, model and key values are never configurable.")
    version = _integer(raw, "schema_version", 1, 2)
    mode, device_id = "direct", ""
    if version == 2:
        mode = _text(raw, "mode", "gateway")
        device_id = _text(raw, "device_id", r"[A-Za-z0-9_-]{22,64}")
    phase = _text(raw, "phase", "startup|pilot|full")
    if phase not in RELEASE_PHASES:
        raise BridgeError("phase_not_released", "Use a released startup or full guided phase; preserve the existing ledger.")
    stage_limit, packet_limit = (MANAGED_PHASES if mode == "gateway" else PHASES)[phase]
    cap = _integer(raw, "allocation_cap", 1, MANAGED_ALLOCATION_LIMIT if mode == "gateway" else ALLOCATION_LIMIT)
    source_root, run_dir, state_dir = (_directory(raw, key) for key in ("source_root", "run_dir", "state_dir"))
    data_dir = _directory(raw, "data_dir") if "data_dir" in raw else (source_root / "data").resolve()
    if not (source_root / "cohort_lab" / "student.py").is_file():
        raise BridgeError("config_invalid", "source_root is not a Studio North lab checkout.")
    if state_dir.is_relative_to(source_root) or state_dir.is_relative_to(run_dir) or source_root.is_relative_to(run_dir):
        raise BridgeError("config_invalid", "state_dir must sit outside the checkout and the run folder; run_dir may not contain the checkout.")
    fingerprint = raw["source_fingerprint"]
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise BridgeError("config_invalid", "source_fingerprint must be the 64-hex value printed by the fingerprint command.")
    ref = raw["credential_ref"]
    shapes = {"env": {"kind", "name"}, "keyring": {"kind", "service", "name"}}
    if not isinstance(ref, dict) or not isinstance(ref.get("kind"), str) or ref["kind"] not in shapes or set(ref) != shapes[ref["kind"]]:
        raise BridgeError("config_invalid", "credential_ref must be an env or keyring reference and never a value.")
    if ref["kind"] == "env":
        credential = {"kind": "env", "name": _text(ref, "name", r"[A-Z][A-Z0-9_]{2,63}")}
    else:
        credential = {"kind": "keyring", "service": _text(ref, "service", r"[A-Za-z0-9_.-]{1,64}"),
                      "name": _text(ref, "name", r"[A-Za-z0-9_.@-]{1,64}")}
    period = _text(raw, "period_id", r"\d{4}-(0[1-9]|1[0-2])")
    if "project_only" in raw and type(raw["project_only"]) is not bool:
        raise BridgeError("config_invalid", "project_only must be a boolean.")
    if period != time.strftime("%Y-%m", time.gmtime()):
        raise BridgeError("config_invalid", "Use the current UTC month for new calls. Prior-period ledgers remain preserved.")
    return BridgeConfig(
        path=path, source_root=source_root, data_dir=data_dir, run_dir=run_dir, state_dir=state_dir,
        subscription_label=_text(raw, "subscription_label", r"[A-Za-z0-9_.-]{1,40}"), period_id=period,
        baseline_tokens=_integer(raw, "baseline_tokens", 0, cap),
        baseline_source=_text(raw, "baseline_source", r"[^\x00-\x1f]{8,200}", limit=200),
        allocation_cap=cap, phase=phase, stage_cap=_integer(raw, "stage_cap", 1, min(stage_limit, cap)),
        packet_max_bytes=_integer(raw, "packet_max_bytes", 2_000, packet_limit) if "packet_max_bytes" in raw else min(packet_limit, 8_000),
        source_fingerprint=fingerprint, credential_ref=credential, mode=mode, device_id=device_id,
        project_only=raw.get("project_only", False))
