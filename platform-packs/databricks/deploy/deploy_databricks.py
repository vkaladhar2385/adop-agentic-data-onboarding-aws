#!/usr/bin/env python3
"""Databricks deploy adapter (Phase 7.3). Gate B validate/plan only."""
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", required=True)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--approve-apply", action="store_true")
    args = ap.parse_args(argv)

    if args.approve_apply:
        print("ERROR: Databricks apply blocked until workspace available.", file=sys.stderr)
        return 2

    rc = _run(["terraform", "init", "-backend=false"])
    if rc == 0 and args.validate:
        rc = _run(["terraform", "validate"])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
