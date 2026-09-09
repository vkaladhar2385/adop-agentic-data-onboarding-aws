"""MCP-equivalent KMS zone key provisioning (boto3 fallback)."""

from __future__ import annotations

from typing import Any


def ensure_zone_keys(
    workload: str,
    zones: list[str],
    *,
    dry_run: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for zone in zones:
        alias = f"alias/{workload}-{zone}"
        if dry_run:
            print(f"[dry-run] core KMS create alias={alias}")
            results.append({"zone": zone, "alias": alias, "status": "planned"})
            continue

        import boto3

        kms = boto3.client("kms")
        try:
            kms.describe_key(KeyId=alias)
            print(f"OK KMS alias exists: {alias}")
            results.append({"zone": zone, "alias": alias, "status": "exists"})
            continue
        except kms.exceptions.NotFoundException:
            pass

        key = kms.create_key(
            Description=f"CMK for {workload} {zone} zone (MCP-owned)",
            KeyUsage="ENCRYPT_DECRYPT",
            Origin="AWS_KMS",
        )
        key_id = key["KeyMetadata"]["KeyId"]
        kms.create_alias(AliasName=alias, TargetKeyId=key_id)
        kms.enable_key_rotation(KeyId=key_id)
        print(f"Created KMS key + alias: {alias}")
        results.append({"zone": zone, "alias": alias, "key_id": key_id, "status": "created"})

    return results
