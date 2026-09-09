#!/usr/bin/env python3
"""Generate .mcp.gateway.json for AgentCore Gateway (Tier B deploy)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "tool-registry" / "servers.yaml"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Gateway MCP client config")
    ap.add_argument("--gateway-url", required=True, help="HTTPS AgentCore Gateway endpoint")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--output", default=str(REPO_ROOT / ".mcp.gateway.json"))
    args = ap.parse_args()

    servers: dict = {}
    if REGISTRY.is_file():
        import yaml

        with REGISTRY.open(encoding="utf-8") as fh:
            registry = yaml.safe_load(fh) or {}
        for name in sorted((registry.get("servers") or {}).keys()):
            servers[name] = {
                "transport": "http",
                "url": args.gateway_url.rstrip("/"),
                "headers": {"x-adop-mcp-server": name},
                "aws": {"region": args.region, "auth": "sigv4"},
            }
    else:
        servers["glue-athena"] = {
            "transport": "http",
            "url": args.gateway_url.rstrip("/"),
            "aws": {"region": args.region, "auth": "sigv4"},
        }

    payload = {"mcpServers": servers}
    out = Path(args.output)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(servers)} server entries)")
    print("Next: python tools/mcp_health_check.py --config .mcp.gateway.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
