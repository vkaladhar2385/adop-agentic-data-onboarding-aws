#!/usr/bin/env python3
"""Phase 0 MCP health check — file/registry preflight (no MCP protocol spawn)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "tool-registry" / "servers.yaml"
MCP_JSON = REPO_ROOT / ".mcp.json"
LOCAL_MCP = REPO_ROOT / "mcp-servers"
DEFAULT_OFFICIAL = REPO_ROOT.parent / "agentic-projects" / "ADOP"

CUSTOM_PATHS = {
    "glue-athena": "mcp-servers/glue-athena-server/server.py",
    "lakeformation": "mcp-servers/lakeformation-server/server.py",
    "sagemaker-catalog": "mcp-servers/sagemaker-catalog-server/server.py",
    "pii-detection": "mcp-servers/pii-detection-server/server.py",
}


def load_registry() -> list[dict]:
    with REGISTRY.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("servers", [])


def load_mcp_names() -> set[str]:
    if not MCP_JSON.is_file():
        return set()
    with MCP_JSON.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return set(data.get("mcpServers", {}).keys())


def find_mcp_root() -> Path | None:
    import os

    for env_key in ("ADOP_MCP_ROOT", "ADOP_OFFICIAL_ROOT"):
        env = os.environ.get(env_key)
        if env and Path(env).is_dir():
            return Path(env).resolve()
    if (LOCAL_MCP / "glue-athena-server" / "server.py").is_file():
        return REPO_ROOT.resolve()
    if DEFAULT_OFFICIAL.is_dir():
        return DEFAULT_OFFICIAL.resolve()
    return None


def check_bin(name: str) -> bool:
    return shutil.which(name) is not None


def check_aws(skip: bool) -> tuple[str, str]:
    if skip:
        return "SKIP", "skipped"
    try:
        proc = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "FAIL", "aws CLI unavailable or timed out"
    if proc.returncode != 0:
        return "FAIL", (proc.stderr or proc.stdout or "sts failed").strip()[:120]
    return "OK", "credentials valid"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-aws", action="store_true", help="Skip aws sts check")
    args = ap.parse_args(argv)

    errors: list[str] = []
    rows: list[tuple[str, str, str, str]] = []

    mcp_root = find_mcp_root()
    if mcp_root is None:
        errors.append(
            f"Vendored MCP tree missing at {LOCAL_MCP} and sibling clone missing at "
            f"{DEFAULT_OFFICIAL}. Copy mcp-servers/ or set ADOP_MCP_ROOT."
        )

    registry = load_registry()
    mcp_names = load_mcp_names()
    reg_names = {s["name"] for s in registry}

    if not MCP_JSON.is_file():
        errors.append("Missing .mcp.json — run: python tools/generate_mcp_config.py")
    elif mcp_names != reg_names:
        missing_json = reg_names - mcp_names
        extra_json = mcp_names - reg_names
        if missing_json:
            errors.append(f".mcp.json missing servers: {sorted(missing_json)}")
        if extra_json:
            errors.append(f".mcp.json extra servers: {sorted(extra_json)}")

    for tool in ("uv", "uvx"):
        status = "OK" if check_bin(tool) else "FAIL"
        rows.append(("tooling", tool, status, "on PATH" if status == "OK" else "install uv"))
        if status == "FAIL":
            errors.append(f"{tool} not on PATH (required for MCP servers)")

    aws_status, aws_detail = check_aws(args.skip_aws)
    rows.append(("tooling", "aws-sts", aws_status, aws_detail))

    for server in registry:
        name = server["name"]
        category = server.get("category", "?")
        if server.get("type") == "custom":
            if mcp_root is None:
                rows.append((category, name, "FAIL", "no mcp-servers root"))
                continue
            rel = server.get("location") or CUSTOM_PATHS.get(name, "")
            script = mcp_root / rel if rel else None
            if script and script.is_file():
                rows.append((category, name, "OK", rel))
            else:
                rows.append((category, name, "FAIL", f"missing {rel}"))
                errors.append(f"Custom server script missing: {script}")
        else:
            pkg = server.get("package", "")
            rows.append((category, name, "OK" if check_bin("uvx") else "FAIL", f"uvx {pkg}"))

    print("\n=== MCP Phase 0 health (Track A) ===\n")
    print(f"{'Tier':<10} {'Server':<18} {'Status':<6} Detail")
    print("-" * 72)
    for tier, name, status, detail in rows:
        print(f"{tier:<10} {name:<18} {status:<6} {detail}")

    required_failed = [
        name for tier, name, status, _ in rows if tier == "REQUIRED" and status != "OK"
    ]
    if required_failed:
        errors.append(f"REQUIRED servers not ready: {required_failed}")

    print()
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print("mcp_health_check: FAIL", file=sys.stderr)
        return 1

    print("mcp_health_check: PASS")
    if mcp_root:
        print(f"MCP script root: {mcp_root}")
    print(f"Configured servers: {len(reg_names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
