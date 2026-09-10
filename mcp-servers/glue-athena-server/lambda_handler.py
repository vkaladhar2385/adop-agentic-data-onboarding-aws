"""
AWS Lambda handler for Glue + Athena MCP Server.

Standalone Lambda function that doesn't require FastMCP.
"""

import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Initialize AWS clients
session = boto3.Session(region_name=os.getenv('AWS_REGION', 'us-east-1'))
glue = session.client('glue')
athena = session.client('athena')


# --- Tool Functions ---

def create_database(name: str, description: str = "") -> dict:
    """Create a Glue Data Catalog database."""
    try:
        glue.create_database(
            DatabaseInput={"Name": name, "Description": description}
        )
        return {"status": "success", "database": name}
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            return {"status": "already_exists", "database": name}
        return {"status": "error", "error": str(e)}


def get_database(name: str) -> dict:
    """Get details of a Glue database."""
    try:
        response = glue.get_database(Name=name)
        db = response['Database']
        return {
            "status": "success",
            "name": db['Name'],
            "description": db.get('Description', ''),
            "location": db.get('LocationUri', '')
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_databases() -> dict:
    """List all Glue databases."""
    try:
        response = glue.get_databases()
        databases = [
            {
                "name": db['Name'],
                "description": db.get('Description', ''),
                "location": db.get('LocationUri', '')
            }
            for db in response['DatabaseList']
        ]
        return {"status": "success", "databases": databases, "count": len(databases)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_tables(database: str) -> dict:
    """List all tables in a Glue database."""
    try:
        response = glue.get_tables(DatabaseName=database)
        tables = [
            {
                "name": table['Name'],
                "type": table.get('TableType', 'EXTERNAL_TABLE'),
                "location": table.get('StorageDescriptor', {}).get('Location', ''),
                "columns": len(table.get('StorageDescriptor', {}).get('Columns', []))
            }
            for table in response['TableList']
        ]
        return {"status": "success", "database": database, "tables": tables, "count": len(tables)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def athena_query(query: str, database: str, workgroup: str = "primary", timeout_seconds: int = 300) -> dict:
    """Execute an Athena query synchronously."""
    try:
        # Start query
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': database},
            WorkGroup=workgroup
        )
        execution_id = response['QueryExecutionId']

        # Poll for completion
        elapsed = 0
        while elapsed < timeout_seconds:
            response = athena.get_query_execution(QueryExecutionId=execution_id)
            state = response['QueryExecution']['Status']['State']

            if state == 'SUCCEEDED':
                # Get results
                results = athena.get_query_results(QueryExecutionId=execution_id, MaxResults=100)
                rows = []
                for row in results['ResultSet']['Rows'][1:]:  # Skip header
                    rows.append([col.get('VarCharValue', '') for col in row['Data']])

                return {
                    "status": "success",
                    "execution_id": execution_id,
                    "rows": rows,
                    "row_count": len(rows)
                }

            if state in ['FAILED', 'CANCELLED']:
                reason = response['QueryExecution']['Status'].get('StateChangeReason', 'Unknown')
                return {"status": "failed", "execution_id": execution_id, "reason": reason}

            time.sleep(1)
            elapsed += 1

        return {
            "status": "timeout",
            "execution_id": execution_id,
            "message": f"Query still running after {timeout_seconds}s"
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


# --- Lambda Handler ---

from shared.mcp_lambda.dispatch import run_tools  # noqa: E402

_TOOL_MAP = {
    "create_database": create_database,
    "get_database": get_database,
    "get_databases": get_databases,
    "get_tables": get_tables,
    "athena_query": athena_query,
}


def handler(event, context):
    """AgentCore Gateway + direct-test compatible MCP handler."""
    return run_tools(
        event,
        context,
        server="glue-athena",
        tool_names=list(_TOOL_MAP.keys()),
        tool_map=_TOOL_MAP,
    )
