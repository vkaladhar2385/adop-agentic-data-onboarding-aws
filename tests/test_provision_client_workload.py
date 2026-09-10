"""Unit tests for provision_client_workload CLI (no AWS)."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_provision_dry_run_supplier_lead_times():
    rc = subprocess.run(
        [
            sys.executable,
            "tools/provision_client_workload.py",
            "--workload",
            "supplier_lead_times",
            "--bucket",
            "test-bucket",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0, rc.stderr
    assert "deploy_workload.py" in rc.stdout or "deploy_workload.py" in rc.stderr


def test_harness_smoke_dry_run():
    rc = subprocess.run(
        [sys.executable, "tools/harness_smoke_test.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0, rc.stderr
    assert "Smoke prompts" in rc.stdout
