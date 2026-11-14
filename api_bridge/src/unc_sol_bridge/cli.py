"""Operator and learner commands: serve, check, fingerprint, templates, install, set-key, live-opening."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import shutil
import sys
import time
import tomllib
from pathlib import Path

from .bridge import Bridge, failure
from .config import BridgeConfig, BridgeError, load_config
from .credentials import check_key, store_key
from .packets import source_fingerprint

SERVER_NAME = "unc_sol"
CLIENTS = {"codex": "codex.config.toml", "claude-code": "claude-code.mcp.json", "vscode": "vscode.mcp.json"}


def render(client: str, config: BridgeConfig) -> str:
    """One server definition per client. It holds a command and a key *reference*; never a key value."""
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    command = str(windowless if os.name == "nt" and windowless.is_file() else executable)
    arguments = ["-m", "unc_sol_bridge", "serve", "--config", str(config.path)]
    variable = config.credential_ref["name"] if config.credential_ref["kind"] == "env" else None
    if client == "codex":
        lines = [f"[mcp_servers.{SERVER_NAME}]", f"command = {json.dumps(command)}", f"args = {json.dumps(arguments)}",
                 "required = false", "enabled = true", "startup_timeout_sec = 20", "tool_timeout_sec = 240"]
        if variable:
            lines.append(f"env_vars = {json.dumps([variable])}")
        return "\n".join(lines) + "\n"
    entry = {"type": "stdio", "command": command, "args": arguments}
    if client == "claude-code":
        if variable:
            entry["env"] = {variable: "${" + variable + "}"}
        return json.dumps({"mcpServers": {SERVER_NAME: entry}}, indent=2) + "\n"
    document = {"servers": {SERVER_NAME: entry}}
    if variable:
        entry["env"] = {variable: "${input:unc-sol-key}"}
        document["inputs"] = [{"type": "promptString", "id": "unc-sol-key", "password": True,
                               "description": "UNC Sol student key (kept by VS Code, never written to this file)"}]
    return json.dumps(document, indent=2) + "\n"


def install(client: str, target, rendered: str) -> str:
    """Add our one definition to an explicitly named client file. Backs up first; never replaces a different definition."""
    target = Path(target)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    try:
        if client == "codex":
            current = tomllib.loads(existing).get("mcp_servers", {}).get(SERVER_NAME)
            wanted = tomllib.loads(rendered)["mcp_servers"][SERVER_NAME]
            unchanged = current == wanted
            updated = existing.rstrip("\n") + ("\n\n" if existing.strip() else "") + rendered
            tomllib.loads(updated if not unchanged else existing)
        else:
            section = "mcpServers" if client == "claude-code" else "servers"
            before = json.loads(existing) if existing.strip() else {}
            document = json.loads(existing) if existing.strip() else {}
            new = json.loads(rendered)
            current, wanted = document.get(section, {}).get(SERVER_NAME), new[section][SERVER_NAME]
            document.setdefault(section, {})[SERVER_NAME] = wanted
            known = {item.get("id") for item in document.get("inputs", []) if isinstance(item, dict)}
            for item in new.get("inputs", []):
                if item["id"] not in known:
                    document.setdefault("inputs", []).append(item)
            unchanged = bool(existing.strip()) and before == document
            updated = json.dumps(document, indent=2) + "\n"
    except (ValueError, AttributeError, TypeError):
        raise BridgeError("install_conflict", "The target file cannot be parsed safely; add the template by hand. Nothing was changed.") from None
    if current not in (None, wanted):
        raise BridgeError("install_conflict", f"{target.name} already defines {SERVER_NAME} differently. Nothing was changed.")
    if unchanged:
        return "unchanged"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name(f"{target.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}"))
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(target)
    return "installed"


def _run(args) -> int:
    if args.command == "serve":
        from .server import serve
        serve(args.config)
        return 0
    if args.command == "fingerprint":
        print(source_fingerprint(Path(args.source_root).resolve()))
        return 0
    if args.command == "prepare":
        from .setup import prepare
        result = prepare(config_path=args.config, source_root=args.source_root, run_dir=args.run_dir,
                         credential_file=args.credential_file, harness=args.harness)
        print(json.dumps(result, indent=2))  # ASCII-safe JSON on Windows console code pages
        return 0 if result["ok"] and not result["problems"] else 1
    config = load_config(args.config)
    if args.command == "check":
        status = Bridge(config).status()
        print(json.dumps(status, indent=2))
        return 1 if status["problems"] else 0
    if args.command == "templates":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for client, filename in CLIENTS.items():
            (out / filename).write_text(render(client, config), encoding="utf-8")
        print(f"wrote {', '.join(CLIENTS.values())} to {out}")
        return 0
    if args.command == "install":
        print(install(args.client, args.target, render(args.client, config)))
        return 0
    if args.command == "set-key":
        store_key(config.credential_ref)
        print("stored in the OS keyring")
        return 0
    if args.command == "relay":
        from .relay import call
        try:
            arguments = json.loads(Path(args.arguments).read_text(encoding="utf-8")) if args.arguments else {}
        except (ValueError, OSError):
            raise BridgeError("invalid_arguments", "The relay arguments file is unreadable; no call was made.") from None
        result = asyncio.run(call(config.path, args.tool, arguments))
        print(json.dumps(result, indent=2))  # the model text remains lossless after JSON decoding
        return 0 if result["ok"] else 1
    # live-opening: the single operator-run startup call. The key lives only in this process's memory.
    key = check_key(sys.stdin.readline() if args.key_stdin else getpass.getpass("UNC Sol key for this one test (hidden): "))
    result = asyncio.run(Bridge(config, api_key=key).ask({"request_id": args.request_id, "intent": "open"}))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="unc-sol-bridge", description="Budget-guarded MCP bridge to UNC gpt-6.1-sol.")
    commands = parser.add_subparsers(dest="command", required=True)
    parsers = {name: commands.add_parser(name) for name in
               ("serve", "check", "fingerprint", "templates", "install", "set-key", "live-opening", "relay", "prepare")}
    for name, sub in parsers.items():
        sub.add_argument("--source-root" if name == "fingerprint" else "--config", required=True)
    parsers["templates"].add_argument("--out", required=True)
    parsers["install"].add_argument("--client", required=True, choices=sorted(CLIENTS))
    parsers["install"].add_argument("--target", required=True)
    parsers["live-opening"].add_argument("--request-id", required=True)
    parsers["live-opening"].add_argument("--key-stdin", action="store_true")
    parsers["relay"].add_argument("--tool", required=True, choices=("sol_status", "sol_preview", "sol_receipt", "sol_ask"))
    parsers["relay"].add_argument("--arguments", help="A small JSON file of tool arguments; never a key, endpoint or model.")
    parsers["prepare"].add_argument("--source-root", required=True)
    parsers["prepare"].add_argument("--run-dir", required=True)
    parsers["prepare"].add_argument("--credential-file", required=True)
    parsers["prepare"].add_argument("--harness", required=True)
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except BridgeError as error:
        print(json.dumps(failure(error)), file=sys.stderr)
        return 2
