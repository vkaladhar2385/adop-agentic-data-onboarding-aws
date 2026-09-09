#!/usr/bin/env python3
"""Fail CI if any workload with config/codegen/*.spec.yaml has drifted artifacts."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    spec_dirs = sorted(REPO_ROOT.glob("workloads/*/config/codegen"))
    if not spec_dirs:
        print("No codegen specs found.")
        return 0
    rc = 0
    for spec_dir in spec_dirs:
        workload = spec_dir.parents[1].name
        print(f"\n=== codegen drift: {workload} ===", flush=True)
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "render_workload.py"),
                "--workload",
                workload,
                "--all",
                "--check-drift",
            ],
            cwd=REPO_ROOT,
        )
        rc = max(rc, proc.returncode)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
