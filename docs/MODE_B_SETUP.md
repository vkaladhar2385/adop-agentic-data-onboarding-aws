# Mode B — Laptop agent + AgentCore Gateway

Official ADOP **Scenario 5a**: agent stays in Cursor; MCP tools for deploy-critical
servers run on **Amazon Bedrock AgentCore Gateway**. Remaining tools stay local (hybrid)
until Lambda targets are added.

## What you get

| Piece | Where |
|-------|--------|
| Main agent | Cursor (laptop) |
| glue-athena, lakeformation | AgentCore Gateway → Lambda |
| iam, core, pii-detection, … | Local stdio (hybrid) |
| Pipelines | Step Functions + Terraform (unchanged) |

## Prerequisites

```powershell
aws login --profile aws-agent
aws sts get-caller-identity --profile aws-agent
```

- AWS CLI v2.15+ with `bedrock-agentcore-control`
- IAM permission to create Lambda, IAM roles, AgentCore Gateway
- Sandbox budget approved (~few dollars/month if Gateway left running)

## One-time setup (commands)

From repo root:

```powershell
# 1. Deploy Gateway + Lambda targets (glue-athena, lakeformation)
python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1

# 2. Switch Cursor to hybrid Mode B
python tools/switch_mcp_mode.py --mode hybrid

# 3. Reload Cursor → Settings → MCP
python tools/mcp_health_check.py --skip-aws
```

## Redeploy pipeline sandbox (after destroy)

```powershell
python tools/deploy_workload.py --workload customer_orders --bucket adop-datalake-199064440913-us-east-1 --auto-provision
```

Or plan-only first:

```powershell
python tools/deploy_workload.py --workload customer_orders --bucket adop-datalake-199064440913-us-east-1 --ensure-tf-module
python tools/deploy_workload.py --workload customer_orders --bucket adop-datalake-199064440913-us-east-1 --approve-apply
python tools/run_e2e_pipeline.py --workload customer_orders --bucket adop-datalake-199064440913-us-east-1
```

## MCP modes

| Mode | Command | Use when |
|------|---------|----------|
| **local** | `python tools/switch_mcp_mode.py --mode local` | Offline dev, no AWS |
| **hybrid** | `--mode hybrid` | **Default Mode B** — Gateway + local |
| **gateway** | `--mode gateway` | Gateway-only (only registered tools work) |

Backup of local config: `.mcp.local.json` (created on first switch).

## Add more Gateway targets

1. Add Lambda handler under `mcp-servers/{name}/lambda_handler.py`
2. Add schema + IAM policy under `config/agentcore/`
3. Append entry to `config/agentcore/gateway_targets.yaml`
4. Re-run `python tools/deploy_mcp_gateway.py`
5. Re-run `python tools/switch_mcp_mode.py --mode hybrid`

## Rollback to local-only

```powershell
python tools/switch_mcp_mode.py --mode local
```

Gateway resources remain in AWS until manually deleted.

## Files

| File | Purpose |
|------|---------|
| `config/agentcore/gateway_targets.yaml` | Targets to deploy |
| `build/mcp/gateway.json` | Deploy metadata (URL, target names) |
| `.mcp.gateway.json` | Gateway-only client config |
| `.mcp.local.json` | Backup of local 13-server config |

## Mode C1 — Harness (cloud agent API)

After Gateway is live, deploy the onboarding agent to **AgentCore Harness**:

```powershell
python tools/deploy_agentcore_harness.py --dry-run
python tools/deploy_agentcore_harness.py --profile aws-agent
python tools/invoke_agentcore_harness.py --prompt "List Glue databases"
```

See **`docs/MODE_C1_HARNESS.md`**. Mode C2 (custom Runtime container) is deferred.
