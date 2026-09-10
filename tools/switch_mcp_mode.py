#!/usr/bin/env python3
"""Switch MCP client config: local | gateway | hybrid (Mode B).

  local   — 13 stdio servers on laptop (.mcp.json from generate_mcp_config)
  gateway — AgentCore Gateway only (cloud tools via semantic routing)
  hybrid  — Gateway for registered targets + local stdio for the rest (recommended Mode B)

Per-server override (when a target is registered on Gateway but you want stdio locally):
  python tools/switch_mcp_mode.py --mode hybrid --local-only iam,core

Usage:
  python tools/switch_mcp_mode.py --mode hybrid
  python tools/switch_mcp_mode.py --mode local
  python tools/switch_mcp_mode.py --mode gateway
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
from shared.deploy.mcp_gateway_client import gateway_mcp_server_entry  # noqa: E402

DEFAULT_AWS_PROFILE = "aws-agent"


def _ensure_local_backup() -> dict:
    if LOCAL_BACKUP.is_file():
        return json.loads(LOCAL_BACKUP.read_text(encoding="utf-8"))
    if not MCP_JSON.is_file():
        subprocess.run([sys.executable, "tools/generate_mcp_config.py"], cwd=REPO_ROOT, check=True)
    shutil.copy2(MCP_JSON, LOCAL_BACKUP)
    return json.loads(MCP_JSON.read_text(encoding="utf-8"))


def _gateway_url(region: str = "us-east-1") -> str:
    if GATEWAY_META.is_file():
        meta = json.loads(GATEWAY_META.read_text(encoding="utf-8"))
        if meta.get("gatewayUrl"):
            return str(meta["gatewayUrl"])
    if GATEWAY_CONFIG.is_file():
        data = json.loads(GATEWAY_CONFIG.read_text(encoding="utf-8"))
        entry = (data.get("mcpServers") or {}).get("agentcore-gateway") or {}
        if entry.get("url"):
            return str(entry["url"])
        args = entry.get("args") or []
        if len(args) >= 2 and str(args[0]).startswith("mcp-proxy-for-aws"):
            return str(args[1])
    raise FileNotFoundError("Missing gateway URL — run tools/deploy_mcp_gateway.py first")


def _gateway_entry(region: str = "us-east-1", profile: str = DEFAULT_AWS_PROFILE) -> dict:
    return gateway_mcp_server_entry(_gateway_url(region), region=region, profile=profile)


def _on_gateway_names() -> set[str]:
    if GATEWAY_META.is_file():
        meta = json.loads(GATEWAY_META.read_text(encoding="utf-8"))
        return set(meta.get("gatewayTargets") or [])
    return set(gateway_target_names(load_gateway_manifest()))


def _parse_local_only(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def build_config(
    mode: str,
    region: str = "us-east-1",
    *,
    local_only: set[str] | None = None,
    aws_profile: str = DEFAULT_AWS_PROFILE,
) -> dict:
    force_local = local_only or set()

    if mode == "local":
        local = _ensure_local_backup()
        return {"mcpServers": dict(local.get("mcpServers") or {})}

    if mode == "gateway":
        merged: dict[str, dict] = {"agentcore-gateway": _gateway_entry(region, aws_profile)}
        if force_local:
            local = _ensure_local_backup()
            for name in force_local:
                cfg = (local.get("mcpServers") or {}).get(name)
                if cfg:
                    merged[name] = cfg
        return {"mcpServers": merged}

    if mode == "hybrid":
        local = _ensure_local_backup()
        on_gateway = _on_gateway_names() - force_local
        merged = {"agentcore-gateway": _gateway_entry(region, aws_profile)}
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
    ap.add_argument(
        "--local-only",
        default="",
        help="Comma-separated server names to keep on local stdio even when registered on Gateway",
    )
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--aws-profile", default=DEFAULT_AWS_PROFILE, help="AWS profile for Gateway SigV4 proxy")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    local_only = _parse_local_only(args.local_only)
    try:
        payload = build_config(
            args.mode,
            args.region,
            local_only=local_only,
            aws_profile=args.aws_profile,
        )
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
    print("Reload Cursor MCP (Settings -> MCP) or restart Cursor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
