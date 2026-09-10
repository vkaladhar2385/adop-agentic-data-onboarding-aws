"""AWS Lambda handler for Lake Formation MCP tools (AgentCore Gateway target)."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import boto3
from botocore.exceptions import ClientError

session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
client = session.client("lakeformation")

TOOLS = [
    "list_lf_tags",
    "create_lf_tag",
    "get_lf_tag",
    "add_lf_tags_to_resource",
    "remove_lf_tags_from_resource",
    "get_resource_lf_tags",
    "grant_permissions",
    "revoke_permissions",
    "batch_grant_permissions",
]


def list_lf_tags() -> dict[str, Any]:
    paginator = client.get_paginator("list_lf_tags")
    tags = []
    for page in paginator.paginate():
        for tag in page.get("LFTags", []):
            tags.append({"tag_key": tag["TagKey"], "tag_values": tag["TagValues"]})
    return {"status": "success", "tags": tags, "count": len(tags)}


def create_lf_tag(tag_key: str, tag_values: list[str]) -> dict[str, Any]:
    try:
        client.create_lf_tag(TagKey=tag_key, TagValues=tag_values)
        return {"status": "success", "tag_key": tag_key, "tag_values": tag_values}
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            return {"status": "already_exists", "tag_key": tag_key}
        return {"status": "error", "error": str(e)}


def get_lf_tag(tag_key: str) -> dict[str, Any]:
    try:
        response = client.get_lf_tag(TagKey=tag_key)
        return {
            "status": "success",
            "tag_key": response["TagKey"],
            "tag_values": response["TagValues"],
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def _table_resource(database: str, table: str, column_names: list[str] | None) -> dict:
    if column_names:
        return {
            "TableWithColumns": {
                "DatabaseName": database,
                "Name": table,
                "ColumnNames": column_names,
            }
        }
    return {"Table": {"DatabaseName": database, "Name": table}}


def add_lf_tags_to_resource(
    database: str,
    table: str,
    lf_tags: list[dict],
    column_names: list[str] | None = None,
) -> dict[str, Any]:
    try:
        client.add_lf_tags_to_resource(
            Resource=_table_resource(database, table, column_names),
            LFTags=lf_tags,
        )
        return {"status": "success", "database": database, "table": table}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def remove_lf_tags_from_resource(
    database: str,
    table: str,
    lf_tags: list[dict],
    column_names: list[str] | None = None,
) -> dict[str, Any]:
    try:
        client.remove_lf_tags_from_resource(
            Resource=_table_resource(database, table, column_names),
            LFTags=lf_tags,
        )
        return {"status": "success", "database": database, "table": table}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_resource_lf_tags(database: str, table: str) -> dict[str, Any]:
    try:
        response = client.get_resource_lf_tags(
            Resource={"Table": {"DatabaseName": database, "Name": table}},
            ShowAssignedLFTags=True,
        )
        return {
            "status": "success",
            "database_tags": response.get("LFTagOnDatabase", []),
            "table_tags": response.get("LFTagsOnTable", []),
            "column_tags": response.get("LFTagsOnColumns", []),
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def grant_permissions(principal_arn: str, permissions: list[str], resource: dict) -> dict[str, Any]:
    try:
        client.grant_permissions(
            Principal={"DataLakePrincipalIdentifier": principal_arn},
            Resource=resource,
            Permissions=permissions,
        )
        return {"status": "success", "principal": principal_arn, "permissions": permissions}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def revoke_permissions(principal_arn: str, permissions: list[str], resource: dict) -> dict[str, Any]:
    try:
        client.revoke_permissions(
            Principal={"DataLakePrincipalIdentifier": principal_arn},
            Resource=resource,
            Permissions=permissions,
        )
        return {"status": "success", "principal": principal_arn}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def batch_grant_permissions(entries: list[dict]) -> dict[str, Any]:
    try:
        client.batch_grant_permissions(Entries=entries)
        return {"status": "success", "count": len(entries)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


TOOL_MAP: dict[str, Callable[..., dict[str, Any]]] = {
    "list_lf_tags": list_lf_tags,
    "create_lf_tag": create_lf_tag,
    "get_lf_tag": get_lf_tag,
    "add_lf_tags_to_resource": add_lf_tags_to_resource,
    "remove_lf_tags_from_resource": remove_lf_tags_from_resource,
    "get_resource_lf_tags": get_resource_lf_tags,
    "grant_permissions": grant_permissions,
    "revoke_permissions": revoke_permissions,
    "batch_grant_permissions": batch_grant_permissions,
}


from shared.mcp_lambda.dispatch import run_tools  # noqa: E402


def handler(event, context):
    return run_tools(
        event,
        context,
        server="lakeformation",
        tool_names=TOOLS,
        tool_map=TOOL_MAP,
    )
