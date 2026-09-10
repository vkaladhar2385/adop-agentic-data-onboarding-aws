"""Redshift Data API MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_rs = _session.client("redshift-data")


def list_workgroups(max_results: int = 20) -> dict[str, Any]:
    try:
        resp = _rs.list_workgroups(MaxResults=min(max_results, 20))
        groups = [
            {"name": w.get("workgroupName"), "status": w.get("status"), "arn": w.get("workgroupArn")}
            for w in resp.get("workgroups", [])
        ]
        return {"workgroups": groups, "count": len(groups)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def execute_statement(
    sql: str,
    database: str,
    workgroup_name: str | None = None,
    cluster_identifier: str | None = None,
    wait_seconds: int = 30,
) -> dict[str, Any]:
    try:
        kwargs: dict[str, Any] = {"Sql": sql, "Database": database}
        if workgroup_name:
            kwargs["WorkgroupName"] = workgroup_name
        if cluster_identifier:
            kwargs["ClusterIdentifier"] = cluster_identifier
        stmt_id = _rs.execute_statement(**kwargs)["Id"]
        deadline = time.time() + wait_seconds
        status = "SUBMITTED"
        while time.time() < deadline:
            desc = _rs.describe_statement(Id=stmt_id)
            status = desc.get("Status", status)
            if status in ("FINISHED", "FAILED", "ABORTED"):
                break
            time.sleep(2)
        result: dict[str, Any] = {"statement_id": stmt_id, "status": status}
        if status == "FINISHED":
            rows = _rs.get_statement_result(Id=stmt_id)
            result["records"] = rows.get("Records", [])[:100]
            result["column_metadata"] = rows.get("ColumnMetadata", [])
        elif status == "FAILED":
            result["error"] = desc.get("Error")
        return result
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"list_workgroups": list_workgroups, "execute_statement": execute_statement}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="redshift",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
