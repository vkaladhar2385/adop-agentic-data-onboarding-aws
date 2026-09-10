"""CloudTrail MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_ct = _session.client("cloudtrail")


def lookup_events(
    lookup_attributes: list[dict[str, str]] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    try:
        end = datetime.fromisoformat(end_time.replace("Z", "+00:00")) if end_time else datetime.now(timezone.utc)
        start = (
            datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if start_time
            else end - timedelta(hours=24)
        )
        resp = _ct.lookup_events(
            LookupAttributes=lookup_attributes or [],
            StartTime=start,
            EndTime=end,
            MaxResults=min(max_results, 50),
        )
        events = [
            {
                "event_name": e.get("EventName"),
                "event_time": e.get("EventTime").isoformat() if e.get("EventTime") else None,
                "username": e.get("Username"),
                "resources": e.get("Resources", []),
            }
            for e in resp.get("Events", [])
        ]
        return {"events": events, "count": len(events)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"lookup_events": lookup_events}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="cloudtrail",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
