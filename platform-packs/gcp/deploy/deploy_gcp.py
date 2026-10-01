#!/usr/bin/env python3
"""GCP deploy adapter (Phase 7.2). Gate B only until a GCP project exists."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TF_DIR = Path(__file__).resolve().parents[1] / "terraform"


def _run(args: list[str]) -> int:
    print(f"$ {' '.join(args)}")
    return subprocess.run(args, cwd=str(TF_DIR)).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GCP (google) deploy adapter")
    ap.add_argument("--workload", required=True)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--approve-apply", action="store_true")
    args = ap.parse_args(argv)

    if args.approve_apply:
        print(
            "ERROR: GCP apply blocked in Phase 7.2 — no GCP project. See docs/PHASE_7_TODO.md.",
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
