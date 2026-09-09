"""MCP-equivalent Glue catalog database create."""

from __future__ import annotations

from typing import Any


def ensure_database(database: str, *, dry_run: bool) -> dict[str, str]:
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

    glue.create_database(DatabaseInput={"Name": database, "Description": f"ADOP {database} (MCP-owned)"})
    print(f"Created database: {database}")
    return {"database": database, "status": "created"}
