"""DynamoDB MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_ddb = _session.client("dynamodb")


def list_tables(max_items: int = 50) -> dict[str, Any]:
    try:
        names: list[str] = []
        resp = _ddb.list_tables(Limit=min(max_items, 100))
        names.extend(resp.get("TableNames", []))
        while resp.get("LastEvaluatedTableName") and len(names) < max_items:
            resp = _ddb.list_tables(
                ExclusiveStartTableName=resp["LastEvaluatedTableName"],
                Limit=min(max_items - len(names), 100),
            )
            names.extend(resp.get("TableNames", []))
        return {"tables": names[:max_items], "count": min(len(names), max_items)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def describe_table(table_name: str) -> dict[str, Any]:
    try:
        resp = _ddb.describe_table(TableName=table_name)["Table"]
        return {
            "table_name": resp["TableName"],
            "status": resp.get("TableStatus"),
            "item_count": resp.get("ItemCount"),
            "size_bytes": resp.get("TableSizeBytes"),
            "key_schema": resp.get("KeySchema", []),
        }
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"list_tables": list_tables, "describe_table": describe_table}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="dynamodb",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
