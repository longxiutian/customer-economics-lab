"""Client-owned stdio MCP server. Initialization and sol_status need neither the provider nor a key."""
import json
import logging
import sys
from typing import Literal

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .bridge import Bridge, _arguments, failure
from .config import BridgeError, load_config

Intent = Literal["open", "teach", "question", "critique", "troubleshoot", "debrief"]
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
PAID = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ARGUMENTS = {
    "sol_status": ((), ()),
    "sol_preview": (("intent", "learner_text", "artifact_ids", "note"), ("intent",)),
    "sol_receipt": (("request_id",), ("request_id",)),
    "sol_ask": (("request_id", "intent", "learner_text", "artifact_ids", "note"), ("request_id", "intent")),
}


class StrictServer(MCPServer):
    """Reject extra/coerced arguments before the SDK can discard them."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.input_schema["additionalProperties"] = False
        return tools

    async def call_tool(self, name, arguments, context=None):
        if name in ARGUMENTS:
            try:
                _arguments(arguments, *ARGUMENTS[name])
            except BridgeError as error:
                return _result(failure(error))
        return await super().call_tool(name, arguments, context)


def _result(payload: dict) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))], structuredContent=payload,
                          isError=not payload["ok"])


def build_server(config_path) -> MCPServer:
    server = StrictServer("unc-sol-bridge")
    cache = {}

    def bridge() -> Bridge:  # lazy: a bad config yields typed tool results instead of a failed startup
        if "bridge" not in cache:
            cache["bridge"] = Bridge(load_config(config_path))
        return cache["bridge"]

    def guarded(action) -> CallToolResult:
        try:
            return _result(action())
        except BridgeError as error:
            return _result(failure(error))

    @server.tool(annotations=READ_ONLY)
    async def sol_status() -> CallToolResult:
        """Zero-cost status: current checkpoint, budget ledger, phase and credential reference. Never contacts UNC Sol."""
        return guarded(lambda: bridge().status())

    @server.tool(annotations=READ_ONLY)
    async def sol_preview(intent: Intent, learner_text: str = "", artifact_ids: list[str] = [], note: str = "") -> CallToolResult:  # noqa: B006
        """Zero-cost dry run: compile the packet for the saved checkpoint and report its size, sources, omissions and reservation."""
        return guarded(lambda: bridge().preview(
            {"intent": intent, "learner_text": learner_text, "artifact_ids": list(artifact_ids), "note": note}))

    @server.tool(annotations=READ_ONLY)
    async def sol_receipt(request_id: str) -> CallToolResult:
        """Zero-cost lookup of one earlier call: ledger state, actual usage and packet source hashes."""
        return guarded(lambda: bridge().receipt({"request_id": request_id}))

    @server.tool(annotations=PAID)
    async def sol_ask(request_id: str, intent: Intent, learner_text: str = "", artifact_ids: list[str] = [], note: str = "") -> CallToolResult:  # noqa: B006
        """One metered UNC gpt-6.1-sol teaching call for the saved checkpoint. The server builds the whole prompt.
        Pass a new unique request_id per learner turn; learner_text must be the learner's literal words. A repeated
        request_id returns the recorded answer without a new call. Never retry a failed call on your own."""
        try:
            return _result(await bridge().ask(
                {"request_id": request_id, "intent": intent, "learner_text": learner_text,
                 "artifact_ids": list(artifact_ids), "note": note}))
        except BridgeError as error:
            return _result(failure(error))

    return server


def serve(config_path) -> None:
    if sys.stderr is not None:  # pythonw may have no stderr; stdout carries protocol frames only
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    build_server(config_path).run(transport="stdio")
