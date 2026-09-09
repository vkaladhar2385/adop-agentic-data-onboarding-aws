"""MCP wiring — registry sync and health check (no live MCP spawn)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_registry_and_mcp_json_exist() -> None:
    assert (REPO_ROOT / "tool-registry" / "servers.yaml").is_file()
    assert (REPO_ROOT / ".mcp.json").is_file()


def test_validate_mcp_registry_passes() -> None:
    result = subprocess.run(
        [sys.executable, "tools/validate_mcp_registry.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_mcp_json_has_thirteen_servers() -> None:
    data = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    names = set(data.get("mcpServers", {}).keys())
    assert len(names) == 13
    assert {"glue-athena", "lakeformation", "iam"}.issubset(names)


def test_health_check_skip_aws() -> None:
    result = subprocess.run(
        [sys.executable, "tools/mcp_health_check.py", "--skip-aws"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if "Vendored MCP tree missing" in result.stderr:
        pytest.skip("mcp-servers/ not present in this environment")
    assert result.returncode == 0, result.stderr or result.stdout
