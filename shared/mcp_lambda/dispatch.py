"""Shared dispatch helpers for AgentCore Gateway Lambda MCP targets."""

from __future__ import annotations

import json
from typing import Any, Callable


def parse_body(event: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    raw = event.get("body", {})
    body = json.loads(raw) if isinstance(raw, str) else raw
    return body.get("tool"), body.get("arguments") or {}


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


def run_tools(
    event: dict[str, Any],
    context: Any,
    *,
    server: str,
    tool_names: list[str],
    tool_map: dict[str, Callable[..., dict[str, Any]]],
) -> dict[str, Any]:
    try:
        tool_name, arguments = parse_body(event)
        if tool_name == "health_check":
            return ok({"server": server, "status": "healthy"})
        if tool_name == "list_tools":
            return ok({"tools": tool_names, "count": len(tool_names)})
        fn = tool_map.get(tool_name or "")
        if not fn:
            return err(404, f"Unknown tool: {tool_name}")
        return ok({"tool": tool_name, "result": fn(**arguments)})
    except TypeError as exc:
        return err(400, f"Invalid arguments: {exc}")
    except Exception as exc:  # noqa: BLE001 — Lambda must return JSON error
        return err(500, str(exc))
