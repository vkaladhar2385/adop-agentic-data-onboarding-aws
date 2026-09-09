#!/usr/bin/env python3
"""MCP Phase 5 infrastructure deploy — catalog, KMS, IAM, Lake Formation (MCP-first order).

Run before Terraform apply when compute.yaml infrastructure.*.owner=mcp.
Fresh sandbox (post-destroy): no terraform state rm required.

Usage:
  python tools/mcp_deploy_infrastructure.py --workload advisory_transactions --dry-run
  python tools/mcp_deploy_infrastructure.py --workload advisory_transactions --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.infrastructure_config import load_infrastructure_owners  # noqa: E402
from shared.deploy.mcp_iam import ensure_pipeline_roles  # noqa: E402
from shared.deploy.mcp_kms import ensure_zone_keys  # noqa: E402
from shared.deploy.mcp_lf import ensure_lf_grants  # noqa: E402
from shared.deploy.mcp_catalog import ensure_database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workload", required=True)
    ap.add_argument("--bucket", default=None, help="Data lake bucket (required for --apply)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only")
    ap.add_argument("--apply", action="store_true", help="Create MCP-owned infrastructure")
    ap.add_argument(
        "--lf-only",
        action="store_true",
        help="Apply Lake Formation grants only (after IAM roles exist)",
    )
    args = ap.parse_args(argv)

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply.", file=sys.stderr)
        return 2

    if args.apply and not args.bucket:
        print("error: --bucket is required with --apply", file=sys.stderr)
        return 1

    dry = args.dry_run or not args.apply
    owners = load_infrastructure_owners(args.workload)

    print(f">>> MCP infrastructure deploy workload={args.workload} dry_run={dry}")
    print(
        f"    owners: catalog={owners['catalog_owner']} kms={owners['kms_owner']} "
        f"iam={owners['iam_owner']} lf={owners['lakeformation_owner']}"
    )

    role_arns: dict[str, str] = {}

    if not args.lf_only:
        if owners["catalog_owner"] == "mcp":
            ensure_database(owners["database"], dry_run=dry)

        if owners["kms_owner"] == "mcp":
            ensure_zone_keys(args.workload, owners["zones"], dry_run=dry)

    if owners["iam_owner"] == "mcp" and not args.lf_only:
        if not args.bucket and not dry:
            print("error: --bucket required for IAM KMS ARN resolution", file=sys.stderr)
            return 1
        bucket = args.bucket or "dry-run-bucket"
        role_arns = ensure_pipeline_roles(
            name_prefix=owners["name_prefix"],
            workload=args.workload,
            bucket=bucket,
            zones=owners["zones"],
            dry_run=dry,
        )

    if owners["lakeformation_owner"] == "mcp":
        glue_arn = role_arns.get("glue")
        lambda_arn = role_arns.get("lambda")
        if owners["iam_owner"] != "mcp" and not dry:
            print("ERROR: lakeformation.owner=mcp requires iam.owner=mcp (need role ARNs)", file=sys.stderr)
            return 1
        if not glue_arn or not lambda_arn:
            if dry:
                glue_arn = glue_arn or f"arn:aws:iam::000000000000:role/{owners['name_prefix']}-glue-role"
                lambda_arn = lambda_arn or f"arn:aws:iam::000000000000:role/{owners['name_prefix']}-lambda-role"
            elif args.lf_only:
                import boto3

                iam = boto3.client("iam")
                glue_arn = iam.get_role(RoleName=f"{owners['name_prefix']}-glue-role")["Role"]["Arn"]
                lambda_arn = iam.get_role(RoleName=f"{owners['name_prefix']}-lambda-role")["Role"]["Arn"]
            else:
                print("ERROR: missing IAM role ARNs for LF grants", file=sys.stderr)
                return 1
        bucket = args.bucket or "dry-run-bucket"
        ensure_lf_grants(
            database=owners["database"],
            bucket=bucket,
            glue_role_arn=glue_arn,
            lambda_role_arn=lambda_arn,
            dry_run=dry,
        )

    print("mcp_deploy_infrastructure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
