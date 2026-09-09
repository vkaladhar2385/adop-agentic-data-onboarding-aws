"""Tests for MCP infrastructure deploy (dry-run, no AWS)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mcp_deploy_infrastructure_dry_run_advisory() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "tools/mcp_deploy_infrastructure.py",
            "--workload",
            "advisory_transactions",
            "--bucket",
            "test-lake",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    out = result.stdout
    assert "advisory_transactions_db" in out
    assert "alias/advisory_transactions-bronze" in out
    assert "glue-role" in out
    assert "lakeformation grant" in out


def test_infrastructure_owners_advisory() -> None:
    from shared.deploy.infrastructure_config import load_infrastructure_owners

    owners = load_infrastructure_owners("advisory_transactions")
    assert owners["catalog_owner"] == "mcp"
    assert owners["kms_owner"] == "mcp"
    assert owners["iam_owner"] == "mcp"
    assert owners["lakeformation_owner"] == "mcp"


def test_main_tf_mcp_owners() -> None:
    main_tf = (REPO_ROOT / "iac/terraform/main.tf").read_text(encoding="utf-8")
    assert 'kms_owner           = "mcp"' in main_tf
    assert 'iam_owner           = "mcp"' in main_tf
    assert 'lakeformation_owner = "mcp"' in main_tf
