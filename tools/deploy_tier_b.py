#!/usr/bin/env python3
"""Tier B steps 13–15 orchestrator (Gateway + optional MWAA demo + E2E).

Default path (cost-conscious):
  Step 13 — AgentCore Gateway health (or local MCP if --skip-gateway)
  Step 14 — SKIPPED unless --mwaa-demo with --mwaa-dags-uri
  Step 15 — Step Functions E2E on a wired workload (default: supplier_lead_times)

Usage:
  python tools/deploy_tier_b.py --dry-run
  python tools/deploy_tier_b.py --skip-gateway --dry-run
  python tools/deploy_tier_b.py --gateway-url https://... --bucket my-lake
  python tools/deploy_tier_b.py --bucket my-lake --mwaa-demo --mwaa-dags-uri s3://.../dags/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AWS_V2 = Path(
    r"C:\Users\vis.sriadibhatla\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe"
)
DEFAULT_E2E_WORKLOAD = "supplier_lead_times"
DEFAULT_MWAA_DEMO = "customer_orders"


def _run(cmd: list[str], *, env: dict | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=REPO_ROOT, check=True, env=env)


def _aws_env(profile: str) -> dict:
    import os

    env = os.environ.copy()
    env["AWS_PROFILE"] = profile
    if AWS_V2.is_file():
        env["PATH"] = str(AWS_V2.parent) + os.pathsep + env.get("PATH", "")
    return env


def aws_identity(profile: str) -> dict:
    aws = str(AWS_V2) if AWS_V2.is_file() else "aws"
    out = subprocess.run(
        [aws, "sts", "get-caller-identity", "--profile", profile, "--output", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "AWS credentials unavailable")
    return json.loads(out.stdout)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--bucket", default=None, help="Data lake bucket for package_and_sync / E2E")
    ap.add_argument("--gateway-url", default=None, help="AgentCore Gateway HTTPS endpoint (step 13)")
    ap.add_argument("--skip-gateway", action="store_true", help="Use local .mcp.json for step 13 check")
    ap.add_argument("--mwaa-demo", action="store_true", help="Run step 14 MWAA DAG sync (demo only)")
    ap.add_argument("--mwaa-dags-uri", default=None)
    ap.add_argument("--e2e-workload", default=DEFAULT_E2E_WORKLOAD)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    print("\n=== Tier B deploy (13–15) ===\n")

    # Preflight local
    _run([sys.executable, "tools/tier_b_acceptance.py", "--workload", DEFAULT_MWAA_DEMO])
    _run([sys.executable, "tools/validate_cedar_policies.py"])

    if args.dry_run:
        print("\nDry-run: local checks only. Re-run without --dry-run after aws login.\n")
        return 0

    try:
        ident = aws_identity(args.profile)
        print(f"AWS account: {ident.get('Account')} arn: {ident.get('Arn')}\n")
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "Fix: run AWS CLI v2 login:\n"
            f'  "{AWS_V2}" login --profile {args.profile}\n',
            file=sys.stderr,
        )
        return 1

    env = _aws_env(args.profile)

    # Step 13 — Gateway config + health
    if args.skip_gateway:
        _run([sys.executable, "tools/mcp_health_check.py", "--skip-aws"], env=env)
        print("\n>>> Step 13: skipped Gateway (--skip-gateway); local MCP preflight OK\n")
    else:
        if not args.gateway_url:
            print(
                "error: --gateway-url required for step 13 (or pass --skip-gateway for local MCP only)",
                file=sys.stderr,
            )
            print(
                "Deploy Gateway per prompts/environment-setup/09-deploy-agentcore-gateway.md",
                file=sys.stderr,
            )
            return 1
        _run(
            [
                sys.executable,
                "tools/generate_mcp_gateway_config.py",
                "--gateway-url",
                args.gateway_url,
            ],
            env=env,
        )
        _run(
            [sys.executable, "tools/mcp_health_check.py", "--config", ".mcp.gateway.json"],
            env=env,
        )
        print("\n>>> Step 13: Gateway config generated; cut over .mcp.json when all servers green\n")

    # Step 14 — MWAA demo (optional)
    if args.mwaa_demo:
        if not args.mwaa_dags_uri:
            print("error: --mwaa-dags-uri required with --mwaa-demo", file=sys.stderr)
            return 1
        _run(
            [
                sys.executable,
                "tools/deploy_workload.py",
                "--workload",
                DEFAULT_MWAA_DEMO,
                "--bucket",
                args.bucket or "REQUIRED",
                "--mwaa-dags-uri",
                args.mwaa_dags_uri,
                "--tier-b-check",
            ],
            env=env,
        )
        print("\n>>> Step 14: MWAA demo DAG synced\n")
    else:
        print("\n>>> Step 14: MWAA skipped (pass --mwaa-demo --mwaa-dags-uri for customer_orders demo)\n")

    # Step 15 — SFN E2E (default orchestrator path)
    if not args.bucket:
        print("error: --bucket required for step 15 E2E (package_and_sync + SFN trigger)", file=sys.stderr)
        return 1

    _run(
        [
            sys.executable,
            "tools/deploy_workload.py",
            "--workload",
            args.e2e_workload,
            "--bucket",
            args.bucket,
            "--dry-run",
            "--tier-b-check",
        ],
        env=env,
    )
    print(
        f"\n>>> Step 15: Run SFN E2E manually after terraform apply:\n"
        f"    aws stepfunctions start-execution --state-machine-arn <arn> "
        f'--input \'{{"workload":"{args.e2e_workload}"}}\' --profile {args.profile}\n'
        f"    Then Athena row-count spot-check on Gold table.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
