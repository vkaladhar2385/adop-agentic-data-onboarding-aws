# Mode C1 — AgentCore Harness + Gateway

**Goal:** Cloud-hosted onboarding agent (API-invokable) using **AgentCore Harness** (managed loop) + **AgentCore Gateway** (MCP tools). Cursor remains available for dev/fallback.

This replaces the outdated official ADOP path that used classic `bedrock-agent create-agent`.

## Architecture

```text
API / CLI invoke_harness
  → AgentCore Harness (adop_onboarding_agent)
      → Bedrock model (Claude)
      → AgentCore Gateway (glue-athena, lakeformation, …)
          → Lambda MCP targets
```

## Prerequisites

| # | Requirement | Command / check |
|---|-------------|-----------------|
| 1 | AWS login | `aws login --profile aws-agent` |
| 2 | Gateway deployed | `python tools/deploy_mcp_gateway.py` |
| 3 | Bedrock model access | Enable `anthropic.claude-sonnet-4-20250514-v1:0` (or edit `config/agentcore/harness.yaml`) |
| 4 | boto3 with Harness API | `python -c "import boto3; boto3.client('bedrock-agentcore-control')"` |

## Deploy Harness

```powershell
# Preview request payload (no AWS)
python tools/deploy_agentcore_harness.py --dry-run

# Create or update harness
python tools/deploy_agentcore_harness.py --profile aws-agent --region us-east-1
```

Writes `build/agentcore/harness.json` with `harnessArn`.

## Test invoke

```powershell
python tools/invoke_agentcore_harness.py --prompt "List Glue databases in this account"
```

Session id must be >= 33 chars (tool generates automatically).

## Configuration

| File | Purpose |
|------|---------|
| `config/agentcore/harness.yaml` | Model, limits, prompt files, tags |
| `config/agentcore/harness_system_prompt.md` | Track A agent instructions |
| `build/mcp/gateway.json` | Gateway ARN source |
| `build/agentcore/harness.json` | Deploy output |

## Known gaps (before production)

1. **Gateway 2/13** — Harness only sees tools registered on Gateway (glue-athena, lakeformation). Expand `config/agentcore/gateway_targets.yaml` for iam, core, pii-detection.
2. **HITL in API mode** — Harness runs autonomously per invoke; approval gates are prompt-based, not Cursor chat. Design explicit pause workflows for deploy.
3. **Pipeline sandbox** — Destroyed; redeploy with `deploy_workload.py --auto-provision` for SFN E2E.
4. **Model ID** — Verify in account: `aws bedrock list-foundation-models --region us-east-1`

## Mode C2 (later)

Custom **AgentCore Runtime** container (ARM64 ECR, `/invocations`) when Harness limits are hit. See `docs/MODE_B_SETUP.md` and official AWS custom Runtime guide.

## Teardown

```powershell
aws bedrock-agentcore-control delete-harness --harness-id <id> --region us-east-1
aws iam delete-role-policy --role-name adop-agentcore-harness-role --policy-name adop-harness-execution
aws iam delete-role --role-name adop-agentcore-harness-role
```
