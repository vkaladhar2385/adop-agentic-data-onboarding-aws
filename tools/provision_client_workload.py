#!/usr/bin/env python3
"""One-command client workload provision (M2): validate, deploy, optional E2E.

Wraps ``tools/deploy_workload.py --auto-provision`` with client-demo defaults.

Usage:
  python tools/provision_client_workload.py --workload supplier_lead_times --bucket my-lake
  python tools/provision_client_workload.py --workload product_inventory --bucket my-lake --dry-run
  python tools/provision_client_workload.py --workload supplier_lead_times --bucket my-lake --no-e2e
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision a client workload end-to-end (M2 wrapper).")
    parser.add_argument("--workload", required=True, help="Workload name under workloads/")
    parser.add_argument("--bucket", required=True, help="Data lake S3 bucket")
    parser.add_argument("--aws-profile", default="aws-agent", help="AWS profile for boto3 + SFN E2E")
    parser.add_argument("--dry-run", action="store_true", help="Validators + pytest only; no AWS changes")
    parser.add_argument("--no-e2e", action="store_true", help="Apply infra but skip landing sync + SFN run")
    parser.add_argument(
        "--mwaa-dags-uri",
        default=None,
        help="When orchestrator=mwaa, sync DAGs to this S3 prefix after package_and_sync",
    )
    args = parser.parse_args(argv)

    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "deploy_workload.py"),
        "--workload",
        args.workload,
        "--bucket",
        args.bucket,
        "--aws-profile",
        args.aws_profile,
        "--ensure-tf-module",
    ]

    if args.dry_run:
        cmd.append("--dry-run")
    else:
        cmd.append("--approve-apply")
        cmd.append("--sync-landing")
        if not args.no_e2e:
            cmd.append("--run-e2e")

    if args.mwaa_dags_uri:
        cmd.extend(["--mwaa-dags-uri", args.mwaa_dags_uri])

    print(">>> provision_client_workload\n", flush=True)
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
