#!/usr/bin/env python3
"""Azure deploy adapter (Phase 7.1).

Wraps `terraform` for the azurerm pack. Gate B (validate/plan) needs no Azure
account; Gate C (apply) is blocked until a subscription exists. This mirrors the
AWS deploy wrapper's build-vs-deploy separation: no apply without an explicit
flag AND human confirmation.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[1]
TF_DIR = PACK_DIR / "terraform"


def _run(args: list[str]) -> int:
    print(f"$ {' '.join(args)}")
    return subprocess.run(args, cwd=str(TF_DIR)).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Azure (azurerm) deploy adapter")
    ap.add_argument("--workload", required=True)
    ap.add_argument("--validate", action="store_true", help="terraform validate (Gate B, no account)")
    ap.add_argument("--plan", action="store_true", help="terraform plan (needs azurerm auth)")
    ap.add_argument("--approve-apply", action="store_true", help="terraform apply (BLOCKED: no sandbox)")
    args = ap.parse_args(argv)

    if args.approve_apply:
        print(
            "ERROR: Azure apply is blocked in Phase 7.1 — no Azure subscription. "
            "Gate C is parked until a sandbox is available (docs/PHASE_7_TODO.md).",
            file=sys.stderr,
        )
        return 2

    rc = _run(["terraform", "init", "-backend=false"])
    if rc == 0 and (args.validate or not args.plan):
        rc = _run(["terraform", "validate"])
    if rc == 0 and args.plan:
        rc = _run(["terraform", "plan", f"-var=workload={args.workload}"])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
