"""SageMaker Catalog custom metadata MCP Lambda for AgentCore Gateway."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_glue = boto3.client("glue", region_name=os.getenv("AWS_REGION", "us-east-1"))


def put_custom_metadata(database: str, table: str, custom_metadata: dict[str, Any]) -> dict[str, Any]:
    try:
        response = _glue.get_table(DatabaseName=database, Name=table)
        table_metadata = response["Table"]
        params = table_metadata.get("Parameters") or {}
        params["custom_metadata"] = json.dumps(custom_metadata)
        table_input = {
            "Name": table_metadata["Name"],
            "StorageDescriptor": table_metadata["StorageDescriptor"],
            "Parameters": params,
        }
        if "PartitionKeys" in table_metadata:
            table_input["PartitionKeys"] = table_metadata["PartitionKeys"]
        _glue.update_table(DatabaseName=database, TableInput=table_input)
        return {"status": "success", "database": database, "table": table}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def get_custom_metadata(database: str, table: str) -> dict[str, Any]:
    try:
        response = _glue.get_table(DatabaseName=database, Name=table)
        params = response["Table"].get("Parameters") or {}
        raw = params.get("custom_metadata", "{}")
        return {"database": database, "table": table, "custom_metadata": json.loads(raw)}
    except (ClientError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {
    "put_custom_metadata": put_custom_metadata,
    "get_custom_metadata": get_custom_metadata,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="sagemaker-catalog",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
