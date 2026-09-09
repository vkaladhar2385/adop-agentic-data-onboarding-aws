#!/usr/bin/env python3
"""Validate tool-registry/servers.yaml matches .mcp.json server names."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "tool-registry" / "servers.yaml"
MCP_JSON = REPO_ROOT / ".mcp.json"


def main() -> int:
    if not REGISTRY.is_file():
        print(f"ERROR: missing {REGISTRY}", file=sys.stderr)
        return 1
    if not MCP_JSON.is_file():
        print(f"ERROR: missing {MCP_JSON} — run tools/generate_mcp_config.py", file=sys.stderr)
        return 1

    with REGISTRY.open(encoding="utf-8") as fh:
        reg = yaml.safe_load(fh)
    yaml_names = {s["name"] for s in reg.get("servers", [])}

    with MCP_JSON.open(encoding="utf-8") as fh:
        mcp = json.load(fh)
    json_names = set(mcp.get("mcpServers", {}).keys())

    errors = []
    if yaml_names - json_names:
        errors.append(f"In registry but not .mcp.json: {sorted(yaml_names - json_names)}")
    if json_names - yaml_names:
        errors.append(f"In .mcp.json but not registry: {sorted(json_names - yaml_names)}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"validate_mcp_registry: OK ({len(yaml_names)} servers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
