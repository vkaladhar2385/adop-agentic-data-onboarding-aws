"""CloudWatch Logs MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_logs = _session.client("logs")


def filter_log_events(
    log_group_name: str,
    filter_pattern: str = "",
    hours_back: int = 1,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        end = int(datetime.now(timezone.utc).timestamp() * 1000)
        start = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp() * 1000)
        resp = _logs.filter_log_events(
            logGroupName=log_group_name,
            filterPattern=filter_pattern or None,
            startTime=start,
            endTime=end,
            limit=min(limit, 100),
        )
        events = [
            {
                "timestamp": e.get("timestamp"),
                "message": e.get("message"),
                "log_stream": e.get("logStreamName"),
            }
            for e in resp.get("events", [])
        ]
        return {"events": events, "count": len(events), "log_group": log_group_name}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"filter_log_events": filter_log_events}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="cloudwatch",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
