"""Codegen spec files validate against contracts/v1 JSON Schemas."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_validate_configs_includes_codegen_specs():
    proc = subprocess.run(
        [sys.executable, "tools/validate_configs.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "codegen specs" in proc.stdout
