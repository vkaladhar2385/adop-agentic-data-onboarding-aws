#!/usr/bin/env python3
"""CodeBuild entry for factory provision (Option B).

Modes (``ADOP_FACTORY_MODE`` env):
  full (default)   — ``deploy_workload.py --approve-apply`` (terraform + sync; required before E2E)
  resync           — validate, pytest, package_and_sync, sync landing only (no terraform)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.sync_landing import sync_landing_data  # noqa: E402


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def main() -> int:
    workload = os.environ.get("ADOP_WORKLOAD", "").strip()
    bucket = os.environ.get("ADOP_BUCKET", "").strip()
    mode = os.environ.get("ADOP_FACTORY_MODE", "full").strip().lower()

    if not workload or not bucket:
        print("error: ADOP_WORKLOAD and ADOP_BUCKET required", file=sys.stderr)
        return 1

    print(f"factory_codebuild_deploy mode={mode} workload={workload} bucket={bucket}", flush=True)

    _run([sys.executable, "tools/validate_configs.py"])
    _run([sys.executable, "tools/validate_compute.py", "--workload", workload])
    _run([sys.executable, "-m", "pytest", f"workloads/{workload}/tests/", "-v"])

    if mode == "full":
        _run(
            [
                sys.executable,
                "tools/deploy_workload.py",
                "--workload",
                workload,
                "--bucket",
                bucket,
                "--approve-apply",
                "--ensure-tf-module",
                "--sync-landing",
            ]
        )
        return 0

    _run(
        [
            sys.executable,
            "tools/package_and_sync.py",
            "--bucket",
            bucket,
            "--workload",
            workload,
        ]
    )
    print(">>> Syncing landing demo data", flush=True)
    sync_landing_data(workload, bucket, profile=None)
    print(">>> Resync complete (no terraform in CodeBuild resync mode)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
