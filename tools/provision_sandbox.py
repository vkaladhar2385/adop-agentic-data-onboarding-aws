#!/usr/bin/env python3
"""Provision ADOP sandbox AWS resources from your laptop.

Brings up AgentCore Gateway (+ optional Harness), deploys workloads via
deploy_workload.py, and switches Cursor to hybrid MCP mode.

Usage (from repo root):
  python tools/provision_sandbox.py --dry-run
  python tools/provision_sandbox.py --bucket adop-datalake-ACCOUNT-us-east-1
  python tools/provision_sandbox.py --bucket ... --workloads advisory_transactions,supplier_lead_times
  python tools/provision_sandbox.py --gateway-only --bucket ...

Prerequisites:
  aws login --profile aws-agent
  cp iac/terraform/terraform.tfvars.example iac/terraform/terraform.tfvars  # fill in values
  cd iac/terraform && terraform init
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.sandbox_lifecycle import provision_sandbox  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Provision ADOP sandbox (Gateway + workloads)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--project", default="adop")
    ap.add_argument("--bucket", default=None, help="Datalake bucket (required unless in terraform.tfvars)")
    ap.add_argument(
        "--workloads",
        default="advisory_transactions",
        help="Comma-separated workloads for deploy_workload --auto-provision",
    )
    ap.add_argument("--gateway-only", action="store_true", help="Deploy Gateway only (no Harness/workloads)")
    ap.add_argument("--skip-gateway", action="store_true")
    ap.add_argument("--skip-harness", action="store_true")
    ap.add_argument("--skip-terraform", action="store_true", help="Skip deploy_workload / pipeline apply")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    workloads = [w.strip() for w in args.workloads.split(",") if w.strip()]
    skip_harness = args.skip_harness or args.gateway_only
    skip_terraform = args.skip_terraform or args.gateway_only
    auto_provision = not args.gateway_only

    print("\n=== ADOP sandbox provision ===\n")
    try:
        result = provision_sandbox(
            profile=args.profile,
            region=args.region,
            project=args.project,
            bucket=args.bucket,
            workloads=workloads,
            skip_gateway=args.skip_gateway,
            skip_harness=skip_harness,
            skip_terraform=skip_terraform,
            auto_provision_workloads=auto_provision,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if args.dry_run:
        print("\nDry-run complete. Re-run without --dry-run to provision.")
    else:
        print("\nProvision complete. Reload Cursor MCP (Settings → MCP).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
