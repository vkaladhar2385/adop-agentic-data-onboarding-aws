#!/usr/bin/env python3
"""Deploy ADOP onboarding agent to AgentCore Harness (Mode C1).

Prerequisites:
  python tools/deploy_mcp_gateway.py

Usage:
  python tools/deploy_agentcore_harness.py --dry-run
  python tools/deploy_agentcore_harness.py --profile aws-agent --region us-east-1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.agentcore_harness import deploy_harness  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy AgentCore Harness for ADOP onboarding")
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--project", default="adop")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        meta = deploy_harness(
            profile=args.profile,
            region=args.region,
            project=args.project,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, RuntimeError, TimeoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(meta, indent=2)[:4000])
        print("\n[dry-run] No AWS changes. Remove --dry-run to deploy.")
        return 0

    print("\nTest invoke:")
    print(
        "  python tools/invoke_agentcore_harness.py "
        '--prompt "List Glue databases in this account"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
