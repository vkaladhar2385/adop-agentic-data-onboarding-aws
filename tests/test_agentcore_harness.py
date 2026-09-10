"""Unit tests for AgentCore Harness config (no AWS)."""

import json

from shared.deploy.agentcore_harness import (
    build_create_harness_request,
    build_system_prompt,
    gateway_arn,
    load_harness_config,
)


def test_load_harness_config_name():
    cfg = load_harness_config()
    assert cfg["name"] == "adop_onboarding_agent"


def test_gateway_arn_format():
    meta = {
        "region": "us-east-1",
        "accountId": "199064440913",
        "gatewayId": "adop-mcp-gateway-ztpftsljts",
    }
    arn = gateway_arn(meta)
    assert arn == "arn:aws:bedrock-agentcore:us-east-1:199064440913:gateway/adop-mcp-gateway-ztpftsljts"


def test_build_create_harness_request_shape():
    cfg = load_harness_config()
    meta = {
        "region": "us-east-1",
        "accountId": "199064440913",
        "gatewayId": "test-gw",
    }
    req = build_create_harness_request(
        cfg,
        execution_role_arn="arn:aws:iam::199064440913:role/test",
        gateway_meta=meta,
    )
    assert req["harnessName"] == "adop_onboarding_agent"
    assert req["tools"][0]["type"] == "agentcore_gateway"
    assert "gatewayArn" in req["tools"][0]["config"]["agentCoreGateway"]
    assert req["model"]["bedrockModelConfig"]["modelId"]
    assert isinstance(req["systemPrompt"], list)
    assert req["systemPrompt"][0]["text"]


def test_system_prompt_includes_track_a_rules():
    cfg = load_harness_config()
    prompt = build_system_prompt(cfg)[0]["text"]
    assert "Human-in-the-loop" in prompt or "Human-in-the-loop" in prompt or "Phase 1" in prompt
    assert "Step Functions" in prompt
