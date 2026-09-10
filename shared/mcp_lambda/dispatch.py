"""Shared dispatch helpers for AgentCore Gateway Lambda MCP targets."""

from __future__ import annotations

import json
from typing import Any, Callable

GATEWAY_TOOL_DELIMITER = "___"


def gateway_tool_name(context: Any) -> str | None:
    """Extract unprefixed tool name from AgentCore Gateway Lambda context."""
    try:
        custom = context.client_context.custom
        raw = custom.get("bedrockAgentCoreToolName") or custom.get("bedrockAgentCoreToolname")
        if not raw:
            return None
        if GATEWAY_TOOL_DELIMITER in raw:
            return raw[raw.index(GATEWAY_TOOL_DELIMITER) + len(GATEWAY_TOOL_DELIMITER) :]
        return str(raw)
    except (AttributeError, KeyError, TypeError):
        return None


def is_gateway_invoke(context: Any) -> bool:
    return gateway_tool_name(context) is not None


def parse_tool_event(event: dict[str, Any], context: Any = None) -> tuple[str | None, dict[str, Any]]:
    """Parse tool name + arguments from Gateway, API Gateway, or direct test invoke."""
    gateway_tool = gateway_tool_name(context) if context is not None else None
    if gateway_tool:
        args = event if isinstance(event, dict) else {}
        return gateway_tool, args

    raw_body = event.get("body", event)
    body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
    if not isinstance(body, dict):
        body = {}

    if body.get("method") == "tools/call":
        params = body.get("params") or {}
        return params.get("name"), params.get("arguments") or {}

    if "toolName" in body:
        return body["toolName"], body.get("arguments") or body.get("input") or {}

    if "name" in body and ("arguments" in body or "input" in body):
        return body["name"], body.get("arguments") or body.get("input") or {}

    if "tool" in body:
        return body.get("tool"), body.get("arguments") or {}

    if "tool" in event:
        return event.get("tool"), event.get("arguments") or {}

    return None, {}


def ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "success", **payload}),
    }


def err(code: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "error", "error": message}),
    }


def gateway_result(payload: dict[str, Any]) -> dict[str, Any]:
    """MCP-compatible tool result for AgentCore Gateway Lambda targets."""
    return payload


def run_tools(
    event: dict[str, Any],
    context: Any,
    *,
    server: str,
    tool_names: list[str],
    tool_map: dict[str, Callable[..., dict[str, Any]]],
) -> dict[str, Any]:
    try:
        tool_name, arguments = parse_tool_event(event, context)
        if tool_name == "health_check":
            payload = {"server": server, "status": "healthy"}
            return gateway_result(payload) if is_gateway_invoke(context) else ok(payload)
        if tool_name == "list_tools":
            payload = {"tools": tool_names, "count": len(tool_names)}
            return gateway_result(payload) if is_gateway_invoke(context) else ok(payload)
        fn = tool_map.get(tool_name or "")
        if not fn:
            if is_gateway_invoke(context):
                raise ValueError(f"Unknown tool: {tool_name}")
            return err(404, f"Unknown tool: {tool_name}")
        result = fn(**arguments)
        if is_gateway_invoke(context):
            return gateway_result(result)
        return ok({"tool": tool_name, "result": result})
    except TypeError as exc:
        if is_gateway_invoke(context):
            raise ValueError(f"Invalid arguments: {exc}") from exc
        return err(400, f"Invalid arguments: {exc}")
    except Exception as exc:
        if is_gateway_invoke(context):
            raise
        return err(500, str(exc))
