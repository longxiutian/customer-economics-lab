"""Key access by reference only: OS keyring or a client-provided environment variable. Values are never printed."""
from __future__ import annotations

import getpass
import os

from .config import BridgeError


class CredentialError(BridgeError):
    """No usable credential. Nothing was reserved or sent."""


def check_key(value) -> str:
    key = value.strip() if isinstance(value, str) else ""
    if not 16 <= len(key) <= 512 or any(not 33 <= ord(character) <= 126 for character in key):
        raise CredentialError("credential_unavailable", "The UNC Sol key reference is empty or malformed; no call was made.")
    return key


def _keyring():
    try:
        import keyring
    except ImportError:
        raise CredentialError("credential_unavailable", "The keyring extra is not installed (uv sync --locked --extra keyring).") from None
    backend = type(keyring.get_keyring())
    label = f"{backend.__module__}.{backend.__name__}".lower()
    if any(word in label for word in ("fail", "null", "plaintext", "keyrings.alt")):
        raise CredentialError("credential_unavailable", "No secure OS keyring backend is available; there is no plaintext fallback.")
    return keyring


def load_key(ref: dict) -> str:
    if ref["kind"] == "env":
        return check_key(os.environ.get(ref["name"]))
    return check_key(_keyring().get_password(ref["service"], ref["name"]))


def describe(ref: dict) -> dict:
    """Reference and availability only. Never reads the keyring entry, so status cannot trigger an OS prompt."""
    if ref["kind"] == "env":
        return {"kind": "env", "name": ref["name"], "present": bool(os.environ.get(ref["name"]))}
    try:
        _keyring()
        available = True
    except CredentialError:
        available = False
    return {"kind": "keyring", "service": ref["service"], "name": ref["name"], "backend_available": available}


def store_key(ref: dict) -> None:
    if ref["kind"] != "keyring":
        raise CredentialError("credential_unavailable", "This configuration uses an environment reference; the client supplies that variable.")
    keyring = _keyring()
    keyring.set_password(ref["service"], ref["name"], check_key(getpass.getpass("UNC Sol student key (hidden): ")))
