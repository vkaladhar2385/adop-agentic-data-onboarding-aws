"""PII detection MCP Lambda for AgentCore Gateway."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.mcp_lambda.dispatch import run_tools

_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
_glue = _session.client("glue")
_lf = _session.client("lakeformation")

PII_PATTERNS = {
    "EMAIL": {"names": ["email", "e_mail", "email_address"], "sensitivity": "HIGH"},
    "PHONE": {"names": ["phone", "telephone", "mobile", "phone_number"], "sensitivity": "HIGH"},
    "SSN": {"names": ["ssn", "social_security", "social_security_number"], "sensitivity": "CRITICAL"},
    "NAME": {"names": ["name", "first_name", "last_name", "full_name"], "sensitivity": "MEDIUM"},
    "ADDRESS": {"names": ["address", "street", "city", "zip", "postal"], "sensitivity": "MEDIUM"},
}


def _detect_pii_in_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for col in columns:
        col_name_lower = col["Name"].lower()
        for pii_type, pattern in PII_PATTERNS.items():
            if col_name_lower in pattern["names"] or any(p in col_name_lower for p in pattern["names"]):
                results.append(
                    {
                        "column": col["Name"],
                        "pii_type": pii_type,
                        "sensitivity": pattern["sensitivity"],
                        "detection_method": "name_based",
                    }
                )
                break
    return results


def detect_pii_in_table(database: str, table: str, apply_tags: bool = False) -> dict[str, Any]:
    try:
        response = _glue.get_table(DatabaseName=database, Name=table)
        columns = response["Table"].get("StorageDescriptor", {}).get("Columns", [])
        columns += response["Table"].get("PartitionKeys", [])
        pii_results = _detect_pii_in_columns(columns)
        if pii_results and apply_tags:
            for result in pii_results:
                try:
                    _lf.add_lf_tags_to_resource(
                        Resource={
                            "TableWithColumns": {
                                "DatabaseName": database,
                                "Name": table,
                                "ColumnNames": [result["column"]],
                            }
                        },
                        LFTags=[
                            {"TagKey": "PII_Classification", "TagValues": [result["sensitivity"]]},
                            {"TagKey": "PII_Type", "TagValues": [result["pii_type"]]},
                        ],
                    )
                except ClientError:
                    pass
        return {
            "database": database,
            "table": table,
            "pii_detected": len(pii_results) > 0,
            "pii_columns": len(pii_results),
            "columns": pii_results,
        }
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


def scan_database_for_pii(database: str, max_tables: int = 20) -> dict[str, Any]:
    try:
        tables_resp = _glue.get_tables(DatabaseName=database)
        summaries = []
        for table in tables_resp.get("TableList", [])[:max_tables]:
            name = table["Name"]
            scan = detect_pii_in_table(database, name, apply_tags=False)
            summaries.append({"table": name, "pii_columns": scan.get("pii_columns", 0)})
        return {"database": database, "tables_scanned": len(summaries), "results": summaries}
    except ClientError as exc:
        return {"status": "error", "error": str(exc)}


_TOOL_MAP = {
    "detect_pii_in_table": detect_pii_in_table,
    "scan_database_for_pii": scan_database_for_pii,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return run_tools(
        event,
        context,
        server="pii-detection",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
