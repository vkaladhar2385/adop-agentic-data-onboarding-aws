"""Cost Explorer MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_ce = _session.client("ce")


def get_cost_and_usage(days_back: int = 7, granularity: str = "DAILY") -> dict[str, Any]:
    try:
        end = date.today()
        start = end - timedelta(days=max(days_back, 1))
        resp = _ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity=granularity,
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        return {"results": resp.get("ResultsByTime", []), "start": start.isoformat(), "end": end.isoformat()}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {"get_cost_and_usage": get_cost_and_usage}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="cost-explorer",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
