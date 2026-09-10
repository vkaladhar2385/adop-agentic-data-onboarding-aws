"""Tests for AgentCore Gateway Lambda dispatch parsing."""

from __future__ import annotations

from types import SimpleNamespace

from shared.mcp_lambda.dispatch import gateway_tool_name, parse_tool_event, run_tools


class _Custom:
    def __init__(self, data: dict):
        self.custom = data


class _Context:
    def __init__(self, tool_name: str):
        self.client_context = _Custom({"bedrockAgentCoreToolName": tool_name})


def test_gateway_tool_name_strips_target_prefix():
    ctx = _Context("glue-athena___get_databases")
    assert gateway_tool_name(ctx) == "get_databases"


def test_parse_tool_event_gateway_uses_event_as_arguments():
    ctx = _Context("factory___trigger_provision")
    event = {"workload": "supplier_lead_times", "bucket": "my-lake", "approve": True}
    tool, args = parse_tool_event(event, ctx)
    assert tool == "trigger_provision"
    assert args == event


def test_parse_tool_event_legacy_body_format():
    event = {"body": {"tool": "get_databases", "arguments": {}}}
    tool, args = parse_tool_event(event)
    assert tool == "get_databases"
    assert args == {}


def test_run_tools_gateway_returns_plain_dict():
    ctx = _Context("core___list_s3_buckets")

    def list_s3_buckets(max_buckets: int = 100) -> dict:
        return {"buckets": [], "count": 0}

    out = run_tools(
        {},
        ctx,
        server="core",
        tool_names=["list_s3_buckets"],
        tool_map={"list_s3_buckets": list_s3_buckets},
    )
    assert out == {"buckets": [], "count": 0}
    assert "statusCode" not in out
