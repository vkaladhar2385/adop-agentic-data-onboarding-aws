"""Unit tests for Cursor Gateway MCP client config (no AWS)."""

from shared.deploy.mcp_gateway_client import PROXY_PACKAGE, gateway_mcp_server_entry


def test_gateway_mcp_server_entry_uses_stdio_proxy():
    entry = gateway_mcp_server_entry(
        "https://example.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        region="us-east-1",
        profile="aws-agent",
    )
    assert entry["command"] == "uvx"
    assert entry["args"][0] == PROXY_PACKAGE
    assert entry["args"][1].startswith("https://")
    assert "--service" in entry["args"]
    assert "bedrock-agentcore" in entry["args"]
    assert entry["env"]["AWS_PROFILE"] == "aws-agent"
    assert entry["env"]["AWS_REGION"] == "us-east-1"
