"""MCP-equivalent Lake Formation grants (boto3 fallback)."""

from __future__ import annotations

import time
from typing import Any


def _register_data_location(lf: Any, bucket: str, *, dry_run: bool) -> None:
    arn = f"arn:aws:s3:::{bucket}"
    if dry_run:
        print(f"[dry-run] lakeformation register_resource {arn}")
        return
    try:
        lf.register_resource(ResourceArn=arn, UseServiceLinkedRole=True)
        print(f"LF registered S3 location: {arn}")
    except lf.exceptions.AlreadyExistsException:
        print(f"LF S3 location already registered: {arn}")
    except Exception as exc:  # noqa: BLE001 — pilot: log and continue if registered elsewhere
        print(f"LF register_resource note ({arn}): {exc}")


def _grant(
    lf: Any,
    *,
    principal: str,
    resource: dict,
    permissions: list[str],
    dry_run: bool,
    label: str,
) -> dict[str, str]:
    if dry_run:
        print(f"[dry-run] lakeformation grant {label} principal={principal} perms={permissions}")
        return {"label": label, "status": "planned"}

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            lf.grant_permissions(
                Principal={"DataLakePrincipalIdentifier": principal},
                Resource=resource,
                Permissions=permissions,
            )
            print(f"LF grant OK: {label}")
            return {"label": label, "status": "granted"}
        except Exception as exc:  # noqa: BLE001 — retry IAM propagation / LF eventual consistency
            last_exc = exc
            if attempt < 3:
                wait = 10 * attempt
                print(f"LF grant retry {label} (attempt {attempt}/3) after {wait}s: {exc}")
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def ensure_lf_grants(
    *,
    database: str,
    bucket: str,
    glue_role_arn: str,
    lambda_role_arn: str,
    dry_run: bool,
) -> list[dict[str, str]]:
    """Mirror workload_pipeline/lakeformation.tf grants when lakeformation.owner=mcp."""
    results: list[dict[str, str]] = []

    if dry_run:
        lf = None
    else:
        import boto3

        lf = boto3.client("lakeformation")
        _register_data_location(lf, bucket, dry_run=False)
        time.sleep(15)

    results.append(
        _grant(
            lf,
            principal=glue_role_arn,
            resource={"Database": {"Name": database}},
            permissions=["CREATE_TABLE", "ALTER", "DROP", "DESCRIBE"],
            dry_run=dry_run,
            label="glue_database",
        )
    )
    results.append(
        _grant(
            lf,
            principal=glue_role_arn,
            resource={"Table": {"DatabaseName": database, "TableWildcard": {}}},
            permissions=["ALL"],
            dry_run=dry_run,
            label="glue_tables",
        )
    )
    results.append(
        _grant(
            lf,
            principal=glue_role_arn,
            resource={"DataLocation": {"ResourceArn": f"arn:aws:s3:::{bucket}"}},
            permissions=["DATA_LOCATION_ACCESS"],
            dry_run=dry_run,
            label="glue_data_location",
        )
    )
    results.append(
        _grant(
            lf,
            principal=lambda_role_arn,
            resource={"Catalog": {}},
            permissions=["CREATE_LF_TAG", "ALTER", "DROP"],
            dry_run=dry_run,
            label="lambda_catalog",
        )
    )
    results.append(
        _grant(
            lf,
            principal=lambda_role_arn,
            resource={"Database": {"Name": database}},
            permissions=["DESCRIBE", "CREATE_TABLE", "ALTER"],
            dry_run=dry_run,
            label="lambda_database",
        )
    )
    results.append(
        _grant(
            lf,
            principal=lambda_role_arn,
            resource={"Table": {"DatabaseName": database, "TableWildcard": {}}},
            permissions=["ALL"],
            dry_run=dry_run,
            label="lambda_tables",
        )
    )
    results.append(
        _grant(
            lf,
            principal=lambda_role_arn,
            resource={"LFTag": {"TagKey": "PII_Type", "TagValues": ["SSN", "EMAIL", "NAME"]}},
            permissions=["ASSOCIATE", "DESCRIBE"],
            dry_run=dry_run,
            label="lambda_lf_tag_pii_type",
        )
    )
    results.append(
        _grant(
            lf,
            principal=lambda_role_arn,
            resource={"LFTag": {"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH"]}},
            permissions=["ASSOCIATE", "DESCRIBE"],
            dry_run=dry_run,
            label="lambda_lf_tag_data_sensitivity",
        )
    )
    return results


def _revoke(
    lf: Any,
    *,
    principal: str,
    resource: dict,
    permissions: list[str],
    dry_run: bool,
    label: str,
) -> dict[str, str]:
    if dry_run:
        print(f"[dry-run] lakeformation revoke {label} principal={principal} perms={permissions}")
        return {"label": label, "status": "planned-revoke"}

    try:
        lf.revoke_permissions(
            Principal={"DataLakePrincipalIdentifier": principal},
            Resource=resource,
            Permissions=permissions,
        )
        print(f"LF revoke OK: {label}")
        return {"label": label, "status": "revoked"}
    except Exception as exc:  # noqa: BLE001 — grant may not exist
        print(f"LF revoke note ({label}): {exc}")
        return {"label": label, "status": "skipped", "reason": str(exc)}


def revoke_lf_grants(
    *,
    database: str,
    bucket: str,
    glue_role_arn: str,
    lambda_role_arn: str,
    dry_run: bool,
) -> list[dict[str, str]]:
    """Revoke grants created by ensure_lf_grants (mirror permissions)."""
    results: list[dict[str, str]] = []
    lf = None if dry_run else __import__("boto3").client("lakeformation")

    grant_specs = [
        ("glue_database", glue_role_arn, {"Database": {"Name": database}}, ["CREATE_TABLE", "ALTER", "DROP", "DESCRIBE"]),
        ("glue_tables", glue_role_arn, {"Table": {"DatabaseName": database, "TableWildcard": {}}}, ["ALL"]),
        ("glue_data_location", glue_role_arn, {"DataLocation": {"ResourceArn": f"arn:aws:s3:::{bucket}"}}, ["DATA_LOCATION_ACCESS"]),
        ("lambda_catalog", lambda_role_arn, {"Catalog": {}}, ["CREATE_LF_TAG", "ALTER", "DROP"]),
        ("lambda_database", lambda_role_arn, {"Database": {"Name": database}}, ["DESCRIBE", "CREATE_TABLE", "ALTER"]),
        ("lambda_tables", lambda_role_arn, {"Table": {"DatabaseName": database, "TableWildcard": {}}}, ["ALL"]),
        ("lambda_lf_tag_pii_type", lambda_role_arn, {"LFTag": {"TagKey": "PII_Type", "TagValues": ["SSN", "EMAIL", "NAME"]}}, ["ASSOCIATE", "DESCRIBE"]),
        ("lambda_lf_tag_data_sensitivity", lambda_role_arn, {"LFTag": {"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH"]}}, ["ASSOCIATE", "DESCRIBE"]),
    ]
    for label, principal, resource, perms in grant_specs:
        results.append(
            _revoke(lf, principal=principal, resource=resource, permissions=perms, dry_run=dry_run, label=label)
        )
    return results
