# Tier B deploy runbook (steps 13–15)

Use after Tier B file work (steps 9–12) passes locally.

## Local preflight (no AWS)

```bash
python tools/deploy_workload.py --workload customer_orders --dry-run --tier-b-check
python tools/tier_b_acceptance.py --workload customer_orders
python tools/validate_cedar_policies.py
```

## Step 13 — AgentCore Gateway

1. Authenticate: `aws login --profile aws-agent` (or your sandbox profile).
2. Deploy Gateway + **14 Lambda targets** (13 registry + `factory`):

```powershell
python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1
python tools/switch_mcp_mode.py --mode gateway --aws-profile aws-agent
python tools/verify_gateway_mcp.py --profile aws-agent
# Reload Cursor → Settings → MCP → enable agentcore-gateway
python tools/mcp_health_check.py --skip-aws
```

3. Optional factory provision module: `python tools/deploy_factory_provision.py --approve-apply`

Full checklist: **`docs/MODE_B_SETUP.md`**. Prompt reference: `prompts/environment-setup/09-deploy-agentcore-gateway.md`.

## Step 14 — MWAA (**optional demo only**)

MWAA is **cost-sensitive** (~$350/mo). **Skip by default.** Use only when demoing
Airflow orchestration for `customer_orders`.

```bash
# Optional demo — after MWAA environment exists
python tools/deploy_tier_b.py --bucket YOUR-LAKE --mwaa-demo \
  --mwaa-dags-uri s3://YOUR-MWAA-BUCKET/dags/ --gateway-url https://...
```

Or sync DAG only:

```bash
python tools/sync_mwaa_dags.py --workload customer_orders --s3-uri s3://YOUR-MWAA-BUCKET/dags/
```

## Step 15 — E2E acceptance (Step Functions default)

**Primary path:** E2E on a Step Functions workload (default `supplier_lead_times`), not MWAA.

```bash
python tools/deploy_tier_b.py --bucket YOUR-LAKE --gateway-url https://YOUR-GATEWAY-URL
# Or skip Gateway for local MCP: --skip-gateway
```

1. `terraform apply` for the SFN workload (after deploy plan approval).
2. Trigger Step Functions execution for the workload state machine.
3. Athena row-count spot-check on Gold table.
4. `python tools/tier_b_acceptance.py --workload customer_orders` (local Cedar/DAG/ontology).

MWAA E2E is **optional** — only when step 14 demo was enabled.

## One-shot orchestrator

```bash
python tools/deploy_tier_b.py --dry-run                    # local only
python tools/deploy_tier_b.py --skip-gateway --bucket X    # SFN E2E prep, no Gateway
python tools/deploy_tier_b.py --gateway-url URL --bucket X # full 13 + 15
```

## Rollback / cost guardrail

- Destroy MWAA when demo ends (same session as `terraform destroy` for other hourly resources).
- Keep local `.mcp.json` (stdio) in git; Gateway config is generated only.
