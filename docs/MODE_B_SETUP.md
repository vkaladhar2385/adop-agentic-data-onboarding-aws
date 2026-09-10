# Mode B — Laptop agent + AgentCore Gateway

Official ADOP **Scenario 5a**: agent stays in Cursor; MCP tools for deploy-critical
servers run on **Amazon Bedrock AgentCore Gateway**. Remaining tools stay local (hybrid)
until Lambda targets are added.

## What you get

| Piece | Where |
|-------|--------|
| Main agent | Cursor (laptop) |
| All 13 MCP servers (manifest) | AgentCore Gateway → Lambda (after deploy) |
| Per-server override | `--local-only` keeps chosen servers on laptop stdio |
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
# 1. Deploy Gateway + all 13 Lambda targets
python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1

# 2. Switch Cursor — pick one:
python tools/switch_mcp_mode.py --mode local      # all 13 stdio on laptop
python tools/switch_mcp_mode.py --mode gateway    # single Gateway endpoint (all cloud)
python tools/switch_mcp_mode.py --mode hybrid     # Gateway + local for unregistered (legacy)
python tools/switch_mcp_mode.py --mode hybrid --local-only iam,core  # mix: cloud + local stdio

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
| **local** | `--mode local` | All 13 stdio on laptop; no Gateway |
| **gateway** | `--mode gateway` | Single Gateway endpoint; all registered tools in AWS |
| **hybrid** | `--mode hybrid` | Gateway for registered targets; local stdio for the rest |
| **hybrid + local-only** | `--mode hybrid --local-only iam,core` | Force named servers to stay local even when on Gateway |

Backup of local config: `.mcp.local.json` (created on first switch).

## Gateway manifest (13/13)

All registry servers are listed in `config/agentcore/gateway_targets.yaml`.
PyPI proxies live under `mcp-servers/gateway-lambdas/`; custom servers use
`mcp-servers/{name}-server/lambda_handler.py`.

After changing the manifest:

1. `python tools/deploy_mcp_gateway.py --profile aws-agent`
2. `python tools/switch_mcp_mode.py --mode gateway` (or hybrid with `--local-only`)

## Rollback to local-only

```powershell
python tools/switch_mcp_mode.py --mode local
```

Gateway resources remain in AWS until you run destroy (below).

## Full sandbox lifecycle (one command from laptop)

**Provision** (Gateway + Harness + workloads):

```powershell
aws login --profile aws-agent
cd iac/terraform; terraform init; cd ../..
python tools/provision_sandbox.py --bucket adop-datalake-199064440913-us-east-1
```

**Destroy** (preview, then confirm):

```powershell
python tools/destroy_sandbox.py --dry-run
python tools/destroy_sandbox.py --yes
python tools/destroy_sandbox.py --yes --include-data   # also empty + delete S3 datalake bucket
python tools/switch_mcp_mode.py --mode local
```

| Flag | Meaning |
|------|---------|
| `--dry-run` | List what would be deleted |
| `--yes` | Required for real destroy |
| `--include-data` | Delete S3 datalake bucket contents |
| `--skip-agentcore` | Terraform + MCP only |
| `--skip-terraform` | AgentCore + MCP Lambdas only |
| `--no-extensions` | Skip Redshift/OpenSearch/Redis on terraform retry |

**KMS caveat:** MCP-owned keys use AWS's mandatory **7-day** pending deletion window — they are scheduled, not gone instantly.

Tags: `config/sandbox_tags.yaml` (`ManagedBy=adop-sandbox`). Destroy scans by tag + name prefix.

See also `docs/SANDBOX_LIFECYCLE.md`.

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
