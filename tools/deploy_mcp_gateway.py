#!/usr/bin/env python3
"""Deploy AgentCore Gateway targets (Mode B) from config/agentcore/gateway_targets.yaml.

Usage:
  python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1
  python tools/switch_mcp_mode.py --mode hybrid   # after deploy
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.agentcore_gateway import deploy_gateway  # noqa: E402
from shared.deploy.mcp_gateway_client import gateway_mcp_server_entry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy AgentCore Gateway + Lambda MCP targets")
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--project", default="adop")
    args = ap.parse_args()

    try:
        meta = deploy_gateway(profile=args.profile, region=args.region, project=args.project)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_path = REPO_ROOT / ".mcp.gateway.json"
    payload = {
        "mcpServers": {
            "agentcore-gateway": gateway_mcp_server_entry(
                meta["gatewayUrl"],
                region=args.region,
                profile=args.profile,
            )
        }
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print("\nNext:")
    print("  python tools/switch_mcp_mode.py --mode hybrid")
    print("  Reload Cursor MCP settings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
