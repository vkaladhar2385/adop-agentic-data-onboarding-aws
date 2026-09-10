"""Factory provision Gateway tools — trigger and poll Option B no-laptop deploy."""

from __future__ import annotations

import os
from typing import Any

from shared.deploy.factory_provision import describe_factory_provision, start_factory_provision
from shared.mcp_lambda.dispatch import run_tools


def trigger_provision(
    workload: str,
    bucket: str,
    approve: bool,
    run_e2e: bool = True,
    session_id: str | None = None,
    requested_by: str | None = None,
) -> dict[str, Any]:
    payload = {
        "workload": workload,
        "bucket": bucket,
        "approve": approve,
        "run_e2e": run_e2e,
    }
    if session_id:
        payload["session_id"] = session_id
    if requested_by:
        payload["requested_by"] = requested_by
    return start_factory_provision(payload, region=os.getenv("AWS_REGION", "us-east-1"))


def get_provision_status(execution_arn: str) -> dict[str, Any]:
    return describe_factory_provision(execution_arn, region=os.getenv("AWS_REGION", "us-east-1"))


_TOOL_MAP = {
    "trigger_provision": trigger_provision,
    "get_provision_status": get_provision_status,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="factory",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
