"""MCP-equivalent Glue catalog database create."""

from __future__ import annotations

from typing import Any

from shared.deploy.sandbox_tags import glue_parameters


def ensure_database(database: str, *, dry_run: bool) -> dict[str, str]:
    params = glue_parameters()
    if dry_run:
        print(f"[dry-run] glue-athena create_database name={database}")
        return {"database": database, "status": "planned"}

    import boto3

    glue = boto3.client("glue")
    try:
        glue.get_database(Name=database)
        print(f"OK database exists: {database}")
        return {"database": database, "status": "exists"}
    except glue.exceptions.EntityNotFoundException:
        pass

    glue.create_database(
        DatabaseInput={
            "Name": database,
            "Description": f"ADOP {database} (MCP-owned)",
            "Parameters": params,
        }
    )
    print(f"Created database: {database}")
    return {"database": database, "status": "created"}
