"""Core AWS MCP proxy (S3, KMS, Secrets Manager) for AgentCore Gateway."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_s3 = _session.client("s3")
_kms = _session.client("kms")
_sm = _session.client("secretsmanager")


def list_s3_buckets(max_buckets: int = 100) -> dict[str, Any]:
    try:
        resp = _s3.list_buckets()
        buckets = [
            {"name": b["Name"], "creation_date": b["CreationDate"].isoformat()}
            for b in resp.get("Buckets", [])[:max_buckets]
        ]
        return {"buckets": buckets, "count": len(buckets)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def list_kms_keys(max_keys: int = 50) -> dict[str, Any]:
    try:
        keys = []
        for page in _kms.get_paginator("list_keys").paginate(PaginationConfig={"MaxItems": max_keys}):
            for key in page.get("Keys", []):
                keys.append({"key_id": key["KeyId"], "arn": key.get("KeyArn")})
        return {"keys": keys, "count": len(keys)}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def describe_secret(secret_id: str) -> dict[str, Any]:
    try:
        resp = _sm.describe_secret(SecretId=secret_id)
        return {
            "name": resp.get("Name"),
            "arn": resp.get("ARN"),
            "last_changed": resp.get("LastChangedDate").isoformat() if resp.get("LastChangedDate") else None,
            "rotation_enabled": resp.get("RotationEnabled", False),
        }
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {
    "list_s3_buckets": list_s3_buckets,
    "list_kms_keys": list_kms_keys,
    "describe_secret": describe_secret,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="core",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
