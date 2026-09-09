#!/usr/bin/env python3
"""Sync rendered Airflow DAGs to MWAA DAG bucket (Tier B deploy)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync workload dags/ to MWAA S3 prefix")
    ap.add_argument("--workload", required=True)
    ap.add_argument("--s3-uri", required=True, help="s3://mwaa-bucket/dags/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wl_dir = REPO_ROOT / "workloads" / args.workload
    dag_dir = wl_dir / "dags"
    if not dag_dir.is_dir():
        print(f"No dags/ directory for {args.workload}. Run render_workload.py first.", file=sys.stderr)
        return 1

    dag_files = sorted(dag_dir.glob("*.py"))
    if not dag_files:
        print(f"No DAG files under {dag_dir}", file=sys.stderr)
        return 1

    for path in dag_files:
        dest = f"{args.s3_uri.rstrip('/')}/{path.name}"
        cmd = ["aws", "s3", "cp", str(path), dest]
        if args.dry_run:
            print("DRY-RUN:", " ".join(cmd))
            continue
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            return proc.returncode
        print(f"Synced {path.name} -> {dest}")

    print("MWAA will pick up DAGs on next scheduler parse (typically < 5 min).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
