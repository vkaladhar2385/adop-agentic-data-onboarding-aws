"""IAM MCP proxy for AgentCore Gateway."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_iam = _session.client("iam")


def get_role(role_name: str) -> dict[str, Any]:
    try:
        role = _iam.get_role(RoleName=role_name)["Role"]
        return {
            "role_name": role["RoleName"],
            "arn": role["Arn"],
            "create_date": role["CreateDate"].isoformat(),
            "path": role.get("Path", "/"),
        }
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def simulate_principal_policy(
    policy_source_arn: str,
    action_names: list[str],
    resource_arns: list[str] | None = None,
) -> dict[str, Any]:
    try:
        resp = _iam.simulate_principal_policy(
            PolicySourceArn=policy_source_arn,
            ActionNames=action_names,
            ResourceArns=resource_arns or ["*"],
        )
        results = [
            {
                "action": r["EvalActionName"],
                "decision": r["EvalDecision"],
                "resource": r.get("EvalResourceName"),
            }
            for r in resp.get("EvaluationResults", [])
        ]
        return {"results": results, "count": len(results)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def list_roles(max_items: int = 50) -> dict[str, Any]:
    try:
        roles = []
        for page in _iam.get_paginator("list_roles").paginate(PaginationConfig={"MaxItems": max_items}):
            for role in page.get("Roles", []):
                roles.append({"role_name": role["RoleName"], "arn": role["Arn"]})
        return {"roles": roles, "count": len(roles)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {
    "get_role": get_role,
    "simulate_principal_policy": simulate_principal_policy,
    "list_roles": list_roles,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="iam",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
