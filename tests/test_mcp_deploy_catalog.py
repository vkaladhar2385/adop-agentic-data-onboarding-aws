"""Tests for MCP catalog deploy helper (dry-run, no AWS)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mcp_deploy_catalog_dry_run_advisory() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "tools/mcp_deploy_catalog.py",
            "--workload",
            "advisory_transactions",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "advisory_transactions_db" in result.stdout


def test_load_rejects_non_mcp_workload() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "tools/mcp_deploy_catalog.py",
            "--workload",
            "product_inventory",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "not mcp" in (result.stderr or result.stdout).lower()


def test_advisory_compute_catalog_owner() -> None:
    import yaml

    path = REPO_ROOT / "workloads/advisory_transactions/config/compute.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["catalog"]["owner"] == "mcp"


def test_main_tf_catalog_owner_mcp() -> None:
    main_tf = (REPO_ROOT / "iac/terraform/main.tf").read_text(encoding="utf-8")
    assert 'catalog_owner       = "mcp"' in main_tf
