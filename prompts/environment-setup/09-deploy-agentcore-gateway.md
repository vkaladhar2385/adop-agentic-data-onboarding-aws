# Deploy Amazon Bedrock AgentCore Gateway (Track B)

> **Admin guide** — host MCP servers behind a unified AgentCore Gateway endpoint.
> Track A local dev uses `.mcp.json` (stdio). Production factory deploy switches to
> Gateway via `switch_mcp_mode.py`.

## When to run

- After Tier A MCP vendoring (`mcp-servers/`) and before Tier B workload E2E on AWS.
- Requires sandbox budget approval and IAM admin (not the onboarding agent).

## Architecture

```
Cursor / Claude (stdio proxy or .mcp.gateway.json)
  → AgentCore Gateway (single HTTPS endpoint)
  → Lambda targets (13 registry servers + factory provision)
  → AWS data plane
```

## Prerequisites

1. AWS CLI ≥ 2.15 with `bedrock-agentcore-control` support
2. `aws login --profile aws-agent`
3. IAM permissions: Gateway create, Lambda invoke, IAM role create

## Steps (this repo)

From repo root:

```powershell
# Deploy Gateway + all 14 Lambda targets from config/agentcore/gateway_targets.yaml
python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1

# Switch Cursor to Gateway (stdio SigV4 proxy — avoids native SSE auth errors)
python tools/switch_mcp_mode.py --mode gateway --aws-profile aws-agent
python tools/verify_gateway_mcp.py --profile aws-agent
# Developer → Reload Window → Settings → MCP → enable agentcore-gateway

python tools/mcp_health_check.py --skip-aws
```

Optional factory provision module (Option B — no-laptop deploy path):

```powershell
python tools/deploy_factory_provision.py --dry-run
python tools/deploy_factory_provision.py --approve-apply
```

## Modes

| Mode | Command |
|------|---------|
| All local stdio | `switch_mcp_mode.py --mode local` |
| Full Gateway | `--mode gateway` |
| Hybrid | `--mode hybrid` or `--mode hybrid --local-only iam,core` |

Full checklist: **`docs/MODE_B_SETUP.md`**. Teardown: **`docs/SANDBOX_LIFECYCLE.md`**.

## Track A notes

- Do **not** run Gateway deploy from a build/onboarding sub-agent (Cedar blocks MCP for sub-agents).
- Official ADOP reference (study only): `../agentic-projects/ADOP/prompts/environment-setup-agent/02-deploy-agentcore-gateway.md`
- Manifest: `config/agentcore/gateway_targets.yaml` (14 targets including `factory`)
