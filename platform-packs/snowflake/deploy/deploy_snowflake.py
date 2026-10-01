#!/usr/bin/env python3
"""Snowflake deploy adapter (Phase 7.4 Mode A). Gate B validate/SQL compile only."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TF_DIR = Path(__file__).resolve().parents[1] / "terraform"


def _run(args: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(args)}")
    return subprocess.run(args, cwd=str(cwd)).returncode


def _compile_sink_sql(workload: str) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "tools/render_workload.py",
            "--workload",
            workload,
            "--artifact",
            "snowflake_sink",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    sql = proc.stdout.strip()
    if not sql.upper().startswith("-- ADOP") and "CREATE OR REPLACE ICEBERG TABLE" not in sql.upper():
        print("ERROR: snowflake_sink SQL compile produced unexpected output", file=sys.stderr)
        return 1
    print(f"OK SQL compile for {workload} ({len(sql)} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", required=True)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--compile-sql", action="store_true")
    ap.add_argument("--approve-apply", action="store_true")
    args = ap.parse_args(argv)

    if args.approve_apply:
        print("ERROR: Snowflake apply blocked until account available.", file=sys.stderr)
        return 2

    rc = 0
    if args.compile_sql:
        rc = _compile_sink_sql(args.workload)
    if rc == 0 and args.validate:
        rc = _run(["terraform", "init", "-backend=false"], TF_DIR)
        if rc == 0:
            rc = _run(["terraform", "validate"], TF_DIR)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
