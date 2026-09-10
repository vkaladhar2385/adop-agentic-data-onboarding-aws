#!/usr/bin/env python3
"""Start factory provision SFN directly (bypass Harness — Option B testing).

Usage:
  python tools/start_provision_api.py --workload supplier_lead_times --bucket my-lake --approve
  python tools/start_provision_api.py --workload supplier_lead_times --bucket my-lake --approve --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.factory_provision import (  # noqa: E402
    build_factory_input,
    start_factory_provision,
    validate_request,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Start factory provision Step Functions (Option B)")
    ap.add_argument("--workload", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--approve", action="store_true", help="Required — simulates Harness APPROVE")
    ap.add_argument("--no-e2e", action="store_true", help="Skip workload pipeline E2E")
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--dry-run", action="store_true", help="Validate only; do not start SFN")
    args = ap.parse_args(argv)

    payload = {
        "workload": args.workload,
        "bucket": args.bucket,
        "approve": args.approve,
        "run_e2e": not args.no_e2e,
    }
    errors = validate_request(payload)
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    body = build_factory_input(payload)
    if args.dry_run:
        print(json.dumps({"status": "VALID", **body}, indent=2))
        return 0

    if not args.approve:
        print("error: pass --approve (human gate)", file=sys.stderr)
        return 1

    try:
        result = start_factory_provision(payload, profile=args.profile, region=args.region)
    except (ValueError, LookupError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
