"""Lambda MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_lam = _session.client("lambda")


def list_functions(max_items: int = 50) -> dict[str, Any]:
    try:
        functions = []
        for page in _lam.get_paginator("list_functions").paginate(PaginationConfig={"MaxItems": max_items}):
            for fn in page.get("Functions", []):
                functions.append(
                    {
                        "name": fn["FunctionName"],
                        "runtime": fn.get("Runtime"),
                        "arn": fn["FunctionArn"],
                        "last_modified": fn.get("LastModified"),
                    }
                )
        return {"functions": functions, "count": len(functions)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def invoke_function(function_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        resp = _lam.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload or {}).encode("utf-8"),
        )
        raw = resp["Payload"].read().decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return {"status_code": resp.get("StatusCode"), "payload": body}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"list_functions": list_functions, "invoke_function": invoke_function}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="lambda",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
