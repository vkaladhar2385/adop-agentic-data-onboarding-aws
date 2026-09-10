#!/usr/bin/env python3
"""Verify AgentCore Gateway MCP config + AWS credentials (Cursor fix preflight).

Usage:
  python tools/verify_gateway_mcp.py --profile aws-agent
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.mcp_gateway_client import gateway_mcp_server_entry  # noqa: E402

GATEWAY_META = REPO_ROOT / "build" / "mcp" / "gateway.json"
CURSOR_MCP = REPO_ROOT / ".cursor" / "mcp.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify Gateway MCP proxy config for Cursor")
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args(argv)

    if not GATEWAY_META.is_file():
        print("error: missing build/mcp/gateway.json — run deploy_mcp_gateway.py first", file=sys.stderr)
        return 1

    meta = json.loads(GATEWAY_META.read_text(encoding="utf-8"))
    url = meta.get("gatewayUrl")
    if not url:
        print("error: gatewayUrl missing in build/mcp/gateway.json", file=sys.stderr)
        return 1

    entry = gateway_mcp_server_entry(url, region=args.region, profile=args.profile)
    print("Expected Cursor entry (agentcore-gateway):")
    print(json.dumps(entry, indent=2))

    if CURSOR_MCP.is_file():
        cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
        live = (cursor.get("mcpServers") or {}).get("agentcore-gateway")
        if live == entry:
            print("\nOK .cursor/mcp.json matches proxy config")
        elif live and live.get("url"):
            print("\nWARN .cursor/mcp.json still uses native url+sse — run switch_mcp_mode.py --mode gateway")
        elif live:
            print("\nWARN .cursor/mcp.json agentcore-gateway differs — re-run switch_mcp_mode.py")
        else:
            print("\nWARN no agentcore-gateway in .cursor/mcp.json")

    try:
        proc = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", args.profile, "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"\nFAIL aws sts: {exc}", file=sys.stderr)
        return 1

    if proc.returncode != 0:
        print(f"\nFAIL aws sts: {(proc.stderr or proc.stdout).strip()}", file=sys.stderr)
        print("Fix: aws login --profile aws-agent  (use AWS CLI v2)", file=sys.stderr)
        return 1

    ident = json.loads(proc.stdout)
    print(f"\nOK AWS credentials: {ident.get('Arn', ident)}")

    if not shutil_which("uvx"):
        print("\nWARN uvx not on PATH — install uv for mcp-proxy-for-aws-cli")
        return 0

    print("\nNext: Developer -> Reload Window, then enable agentcore-gateway in Settings -> MCP")
    return 0


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


if __name__ == "__main__":
    raise SystemExit(main())
