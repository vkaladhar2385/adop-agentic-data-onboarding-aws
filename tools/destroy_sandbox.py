#!/usr/bin/env python3
"""Destroy all ADOP sandbox AWS resources from your laptop.

Removes AgentCore (Harness, Gateway, MCP Lambdas), Terraform pipelines,
MCP-owned KMS/Glue/IAM, optional S3 datalake data, and ADOP log groups.

Usage (from repo root):
  python tools/destroy_sandbox.py --dry-run
  python tools/destroy_sandbox.py --yes
  python tools/destroy_sandbox.py --yes --include-data --bucket adop-datalake-ACCOUNT-us-east-1

Notes:
  - KMS keys enter a mandatory 7-day pending deletion window (AWS limit).
  - Requires AWS credentials: aws login --profile aws-agent
  - Terraform uses aws-agent-terraform profile (same as deploy_workload.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.sandbox_lifecycle import destroy_sandbox  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Destroy ADOP sandbox AWS resources (one command teardown)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--profile", default="aws-agent", help="AWS profile for boto3")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--project", default="adop", help="Resource name prefix")
    ap.add_argument("--bucket", default=None, help="Datalake bucket (auto from terraform.tfvars if omitted)")
    ap.add_argument(
        "--include-data",
        action="store_true",
        help="Empty and delete the S3 datalake bucket (destructive)",
    )
    ap.add_argument(
        "--no-extensions",
        action="store_true",
        help="Skip Redshift/OpenSearch/Redis terraform modules on targeted retry",
    )
    ap.add_argument("--skip-terraform", action="store_true", help="Only remove AgentCore + MCP assets")
    ap.add_argument("--skip-agentcore", action="store_true", help="Only run terraform + MCP cleanup")
    ap.add_argument("--no-revoke-lf", action="store_true", help="Skip Lake Formation grant revocation")
    ap.add_argument("--no-disable-bedrock-logging", action="store_true", help="Leave Bedrock invocation logging as-is")
    ap.add_argument("--dry-run", action="store_true", help="Print planned deletes only")
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Required to perform destructive destroy (omit for dry-run only)",
    )
    args = ap.parse_args(argv)

    if not args.dry_run and not args.yes:
        print("Refusing to destroy without --yes. Run with --dry-run first to preview.", file=sys.stderr)
        return 2

    print("\n=== ADOP sandbox destroy ===\n")
    report = destroy_sandbox(
        profile=args.profile,
        region=args.region,
        project=args.project,
        bucket=args.bucket,
        include_data=args.include_data,
        include_extensions=not args.no_extensions,
        skip_terraform=args.skip_terraform,
        skip_agentcore=args.skip_agentcore,
        revoke_lf=not args.no_revoke_lf,
        disable_bedrock_logging=not args.no_disable_bedrock_logging,
        dry_run=args.dry_run,
    )

    print("\n--- Summary ---")
    print(f"Deleted/planned: {len(report.deleted)}")
    print(f"Skipped (not found): {len(report.skipped)}")
    if report.pending:
        print("\nPending (AWS minimum wait):")
        for item in report.pending:
            print(f"  - {item}")
    if report.warnings:
        print("\nWarnings:")
        for item in report.warnings:
            print(f"  - {item}")

    if report.warnings and not args.dry_run:
        print("\nRe-run verify: python tools/destroy_sandbox.py --dry-run --skip-terraform --skip-agentcore")
        return 1

    if args.dry_run:
        print("\nDry-run complete. Re-run with --yes to destroy.")
    else:
        print("\nDestroy complete. Switch Cursor to local MCP:")
        print("  python tools/switch_mcp_mode.py --mode local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
