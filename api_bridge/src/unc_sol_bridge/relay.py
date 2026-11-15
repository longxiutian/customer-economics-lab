"""Call the same stdio MCP from the current chat without reloading its client.

This is an explicit SDK client, not a direct API or native-provider fallback.
The child exits after one tool call; all budgets and receipts remain durable.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import BridgeError, load_config

TOOLS = ("sol_status", "sol_preview", "sol_receipt", "sol_ask")


async def call(config_path, tool, arguments):
    if tool not in TOOLS:
        raise BridgeError("invalid_tool", "Use a released Studio North MCP tool.")
    config = load_config(config_path)
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    command = str(windowless if os.name == "nt" and windowless.is_file() else executable)
    # Do not leak the harness's unrelated credentials to the child.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
               "LOCALAPPDATA", "APPDATA", "HOME", "LANG", "PYTHONIOENCODING"}
    if config.credential_ref["kind"] == "env":
        allowed.add(config.credential_ref["name"].upper())
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["PYTHONIOENCODING"] = "utf-8"
    params = StdioServerParameters(command=command,
                                  args=["-m", "unc_sol_bridge", "serve", "--config", str(config.path)],
                                  env=env, cwd=str(config.source_root))
    try:
        async with asyncio.timeout(230):
            with open(os.devnull, "w", encoding="utf-8") as errlog:
                async with stdio_client(params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=210) as session:
                        await session.initialize()
                        result = await session.call_tool(tool, arguments)
                        if result.structured_content is None:
                            raise BridgeError("mcp_result_invalid", "The MCP returned no structured result; no automatic retry.",
                                              provider_called="unknown", charge="unknown; inspect the durable ledger")
                        return result.structured_content
    except BridgeError:
        raise
    except (Exception, BaseExceptionGroup) as error:
        # An outer failure cannot establish whether the child already dispatched.
        raise BridgeError("mcp_unavailable", "The MCP relay did not finish. Check the local receipt/status before any new call.",
                          error_type=type(error).__name__, provider_called="unknown", charge="unknown; inspect the durable ledger") from None
