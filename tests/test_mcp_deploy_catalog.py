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


def test_load_rejects_terraform_owned_catalog(tmp_path: Path) -> None:
    from tools.mcp_deploy_catalog import load_catalog_config

    wl = tmp_path / "workloads" / "tf_catalog"
    (wl / "config").mkdir(parents=True)
    (wl / "config" / "compute.yaml").write_text(
        "workload: tf_catalog\ninfrastructure:\n  catalog:\n    owner: terraform\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not mcp"):
        load_catalog_config("tf_catalog", repo_root=tmp_path)


def test_product_inventory_defaults_to_mcp_catalog() -> None:
    from tools.mcp_deploy_catalog import load_catalog_config

    cfg = load_catalog_config("product_inventory")
    assert cfg["owner"] == "mcp"
    assert cfg["database"] == "product_inventory_db"


def test_advisory_compute_catalog_owner() -> None:
    import yaml

    path = REPO_ROOT / "workloads/advisory_transactions/config/compute.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["catalog"]["owner"] == "mcp"


def test_main_tf_catalog_owner_mcp() -> None:
    main_tf = (REPO_ROOT / "iac/terraform/main.tf").read_text(encoding="utf-8")
    assert 'catalog_owner       = "mcp"' in main_tf
