# Deploy Amazon Bedrock AgentCore Gateway (Track B)

> **Admin guide** — host MCP servers behind a unified AgentCore Gateway endpoint.
> Track A local dev uses `.mcp.json` (stdio). Production factory deploy switches to
> `.mcp.gateway.json` (HTTPS + SigV4).

## When to run

- After Tier A MCP vendoring (`mcp-servers/`) and before Tier B workload #5 E2E on AWS.
- Requires sandbox budget approval and IAM admin (not the onboarding agent).

## Architecture

```
Cursor / Claude (.mcp.gateway.json)
  → AgentCore Gateway (single HTTPS endpoint)
  → Lambda targets (glue-athena, lakeformation, sagemaker-catalog, pii-detection, …)
  → AWS data plane
```

## Prerequisites

1. AWS CLI ≥ 2.15 with `bedrock-agentcore-control` support
2. Lambda MCP targets deployed from `mcp-servers/` (see each server's README)
3. IAM permissions: Gateway create, Lambda invoke, IAM role create

## Steps (summary)

1. **Create Gateway IAM role** — trust `bedrock-agentcore.amazonaws.com`, attach Lambda invoke policy.
2. **Create Gateway** — `aws bedrock-agentcore-control create-gateway …`
3. **Register targets** — one target per MCP server; upload tool OpenAPI/schema JSON.
4. **Generate config** — `python tools/generate_mcp_gateway_config.py --gateway-url … --region us-east-1`
5. **Health check** — `python tools/mcp_health_check.py --config .mcp.gateway.json`
6. **Cutover** — copy `.mcp.gateway.json` → `.mcp.json` only after all 13 servers green.

## Track A notes

- Official full command sequence lives in sibling repo:
  `../agentic-projects/ADOP/prompts/environment-setup-agent/02-deploy-agentcore-gateway.md`
- Do **not** run Gateway deploy from a build/onboarding sub-agent (Cedar blocks MCP for sub-agents).
- Post-deploy: run post-deployment verifier + Step Functions or MWAA E2E per workload.

## Rollback

Keep local `.mcp.json` (stdio) in git; Gateway config is generated artifact — regenerate from
`tools/generate_mcp_gateway_config.py` after destroy/recreate.
