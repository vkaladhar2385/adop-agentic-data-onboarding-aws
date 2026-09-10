#!/usr/bin/env python3
"""Switch MCP client config: local | gateway | hybrid (Mode B).

  local   — 13 stdio servers on laptop (.mcp.json from generate_mcp_config)
  gateway — AgentCore Gateway only (cloud tools via semantic routing)
  hybrid  — Gateway for registered targets + local stdio for the rest (recommended Mode B)

Usage:
  python tools/switch_mcp_mode.py --mode hybrid
  python tools/switch_mcp_mode.py --mode local
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_BACKUP = REPO_ROOT / ".mcp.local.json"
GATEWAY_CONFIG = REPO_ROOT / ".mcp.gateway.json"
MCP_JSON = REPO_ROOT / ".mcp.json"
CURSOR_MCP = REPO_ROOT / ".cursor" / "mcp.json"
GATEWAY_META = REPO_ROOT / "build" / "mcp" / "gateway.json"

sys.path.insert(0, str(REPO_ROOT))
from shared.deploy.agentcore_gateway import gateway_target_names, load_gateway_manifest  # noqa: E402


def _ensure_local_backup() -> dict:
    if LOCAL_BACKUP.is_file():
        return json.loads(LOCAL_BACKUP.read_text(encoding="utf-8"))
    if not MCP_JSON.is_file():
        subprocess.run([sys.executable, "tools/generate_mcp_config.py"], cwd=REPO_ROOT, check=True)
    shutil.copy2(MCP_JSON, LOCAL_BACKUP)
    return json.loads(MCP_JSON.read_text(encoding="utf-8"))


def _gateway_entry(region: str = "us-east-1") -> dict:
    if not GATEWAY_CONFIG.is_file():
        raise FileNotFoundError("Missing .mcp.gateway.json — run tools/deploy_mcp_gateway.py first")
    data = json.loads(GATEWAY_CONFIG.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    if "agentcore-gateway" in servers:
        return servers["agentcore-gateway"]
    if GATEWAY_META.is_file():
        meta = json.loads(GATEWAY_META.read_text(encoding="utf-8"))
        return {
            "url": meta["gatewayUrl"],
            "transport": "sse",
            "auth": {
                "type": "aws-sigv4",
                "service": "bedrock-agentcore",
                "region": meta.get("region", region),
            },
        }
    raise ValueError("No agentcore-gateway entry in .mcp.gateway.json")


def _on_gateway_names() -> set[str]:
    if GATEWAY_META.is_file():
        meta = json.loads(GATEWAY_META.read_text(encoding="utf-8"))
        return set(meta.get("gatewayTargets") or [])
    return set(gateway_target_names(load_gateway_manifest()))


def build_config(mode: str, region: str = "us-east-1") -> dict:
    if mode == "local":
        local = _ensure_local_backup()
        return {"mcpServers": dict(local.get("mcpServers") or {})}

    if mode == "gateway":
        return {"mcpServers": {"agentcore-gateway": _gateway_entry(region)}}

    if mode == "hybrid":
        local = _ensure_local_backup()
        on_gateway = _on_gateway_names()
        merged = {"agentcore-gateway": _gateway_entry(region)}
        for name, cfg in (local.get("mcpServers") or {}).items():
            if name not in on_gateway:
                merged[name] = cfg
        return {"mcpServers": merged}

    raise ValueError(f"Unknown mode: {mode}")


def write_configs(payload: dict) -> None:
    text = json.dumps(payload, indent=2) + "\n"
    MCP_JSON.write_text(text, encoding="utf-8")
    CURSOR_MCP.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_MCP.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Switch MCP mode for Cursor / Claude")
    ap.add_argument("--mode", choices=("local", "gateway", "hybrid"), required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        payload = build_config(args.mode, args.region)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    names = sorted(payload["mcpServers"].keys())
    print(f"Mode {args.mode}: {len(names)} MCP entries -> {names}")
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    write_configs(payload)
    print(f"Updated {MCP_JSON} and {CURSOR_MCP}")
    print("Reload Cursor MCP (Settings → MCP) or restart Cursor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
