"""Cursor-compatible MCP client config for AgentCore Gateway (stdio SigV4 proxy).

Cursor often fails on native ``url`` + ``auth.aws-sigv4`` for AgentCore Gateway.
Use AWS ``mcp-proxy-for-aws-cli`` as a stdio bridge — same pattern as AWS docs.
"""

from __future__ import annotations

PROXY_PACKAGE = "mcp-proxy-for-aws-cli@latest"
GATEWAY_SERVICE = "bedrock-agentcore"


def gateway_mcp_server_entry(
    gateway_url: str,
    *,
    region: str = "us-east-1",
    profile: str = "aws-agent",
) -> dict:
    """Return a ``mcpServers`` entry for ``agentcore-gateway`` (stdio + uvx proxy)."""
    url = gateway_url.rstrip("/")
    return {
        "command": "uvx",
        "args": [
            PROXY_PACKAGE,
            url,
            "--service",
            GATEWAY_SERVICE,
            "--region",
            region,
            "--profile",
            profile,
        ],
        "env": {
            "AWS_PROFILE": profile,
            "AWS_REGION": region,
            "AWS_SDK_LOAD_CONFIG": "1",
        },
    }
