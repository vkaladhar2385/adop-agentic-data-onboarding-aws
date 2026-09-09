from shared.utils.cedar_policy import CedarPolicyEvaluator, AgentPrincipal, McpTool, sub_agent_mcp_denied


def test_sub_agent_mcp_denied_for_metadata():
    allowed, reason = sub_agent_mcp_denied("metadata")
    assert allowed is False
    assert "MCP" in reason or "DENY" in reason


def test_sub_agent_mcp_denied_for_transformation():
    allowed, _ = sub_agent_mcp_denied("transformation")
    assert allowed is False


def test_onboarding_main_can_invoke_mcp():
    evaluator = CedarPolicyEvaluator()
    agent = AgentPrincipal(agent_type="onboarding", execution_context="main_conversation")
    tool = McpTool(server_name="glue-athena", tool_name="run_query")
    allowed, _ = evaluator.is_authorized(agent, "InvokeTool", tool)
    assert allowed is True
