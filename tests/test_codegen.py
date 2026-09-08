"""Schema validation for workload configs."""
from pathlib import Path

import subprocess
import sys


def test_validate_configs_passes():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo / "tools" / "validate_configs.py")],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_bronze_to_silver_no_codegen_drift():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "render_workload.py"),
            "--workload",
            "advisory_transactions",
            "--artifact",
            "bronze_to_silver",
            "--check-drift",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
