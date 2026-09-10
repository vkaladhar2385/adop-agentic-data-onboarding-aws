"""S3 Tables MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_s3tables = _session.client("s3tables")


def list_table_buckets(max_results: int = 50) -> dict[str, Any]:
    try:
        resp = _s3tables.list_table_buckets(MaxResults=min(max_results, 50))
        buckets = [
            {
                "name": b.get("name"),
                "arn": b.get("arn"),
                "created_at": b.get("createdAt").isoformat() if b.get("createdAt") else None,
            }
            for b in resp.get("tableBuckets", [])
        ]
        return {"table_buckets": buckets, "count": len(buckets)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def list_tables(table_bucket_arn: str, namespace: str, max_results: int = 50) -> dict[str, Any]:
    try:
        resp = _s3tables.list_tables(
            TableBucketARN=table_bucket_arn,
            Namespace=namespace,
            MaxResults=min(max_results, 50),
        )
        tables = [{"name": t.get("name"), "arn": t.get("tableARN")} for t in resp.get("tables", [])]
        return {"tables": tables, "count": len(tables), "namespace": namespace}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"list_table_buckets": list_table_buckets, "list_tables": list_tables}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="s3-tables",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
