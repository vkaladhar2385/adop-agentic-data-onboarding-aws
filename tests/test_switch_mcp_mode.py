"""Unit tests for MCP mode switching (no AWS)."""

import json
from pathlib import Path

import tools.switch_mcp_mode as switch


def test_hybrid_includes_gateway_and_local_servers(monkeypatch, tmp_path):
    repo = tmp_path
    local = {
        "mcpServers": {
            "glue-athena": {"command": "uv"},
            "lakeformation": {"command": "uv"},
            "iam": {"command": "uvx"},
        }
    }
    (repo / ".mcp.local.json").write_text(json.dumps(local), encoding="utf-8")
    (repo / ".mcp.gateway.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "agentcore-gateway": {
                        "url": "https://example.gateway/mcp",
                        "transport": "sse",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    meta_dir = repo / "build" / "mcp"
    meta_dir.mkdir(parents=True)
    (meta_dir / "gateway.json").write_text(
        json.dumps({"gatewayUrl": "https://example.gateway/mcp", "gatewayTargets": ["glue-athena", "lakeformation"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(switch, "REPO_ROOT", repo)
    monkeypatch.setattr(switch, "LOCAL_BACKUP", repo / ".mcp.local.json")
    monkeypatch.setattr(switch, "GATEWAY_CONFIG", repo / ".mcp.gateway.json")
    monkeypatch.setattr(switch, "GATEWAY_META", repo / "build" / "mcp" / "gateway.json")

    payload = switch.build_config("hybrid")
    names = set(payload["mcpServers"].keys())
    assert "agentcore-gateway" in names
    assert "iam" in names
    assert "glue-athena" not in names
    assert "lakeformation" not in names


def test_gateway_target_names_from_manifest():
    from shared.deploy.agentcore_gateway import gateway_target_names

    names = gateway_target_names()
    assert "glue-athena" in names
    assert "lakeformation" in names
    assert len(names) == 13


def test_hybrid_local_only_keeps_stdio_server(monkeypatch, tmp_path):
    repo = tmp_path
    local = {
        "mcpServers": {
            "glue-athena": {"command": "uv"},
            "iam": {"command": "uvx"},
        }
    }
    (repo / ".mcp.local.json").write_text(json.dumps(local), encoding="utf-8")
    (repo / ".mcp.gateway.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "agentcore-gateway": {
                        "url": "https://example.gateway/mcp",
                        "transport": "sse",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    meta_dir = repo / "build" / "mcp"
    meta_dir.mkdir(parents=True)
    (meta_dir / "gateway.json").write_text(
        json.dumps(
            {
                "gatewayUrl": "https://example.gateway/mcp",
                "gatewayTargets": ["glue-athena", "iam"],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(switch, "REPO_ROOT", repo)
    monkeypatch.setattr(switch, "LOCAL_BACKUP", repo / ".mcp.local.json")
    monkeypatch.setattr(switch, "GATEWAY_CONFIG", repo / ".mcp.gateway.json")
    monkeypatch.setattr(switch, "GATEWAY_META", repo / "build" / "mcp" / "gateway.json")

    payload = switch.build_config("hybrid", local_only={"iam"})
    names = set(payload["mcpServers"].keys())
    assert "agentcore-gateway" in names
    assert "iam" in names
    assert "glue-athena" not in names
