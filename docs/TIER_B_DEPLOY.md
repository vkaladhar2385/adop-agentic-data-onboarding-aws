# Tier B deploy runbook (steps 13–15)

Use after Tier B file work (steps 9–12) passes locally.

## Local preflight (no AWS)

```bash
python tools/deploy_workload.py --workload customer_orders --dry-run --tier-b-check
python tools/tier_b_acceptance.py --workload customer_orders
python tools/validate_cedar_policies.py
```

## Step 13 — AgentCore Gateway

1. Authenticate: `aws login` or refresh sandbox credentials.
2. Follow `prompts/environment-setup/09-deploy-agentcore-gateway.md` (full commands in sibling official ADOP repo).
3. Generate client config:

```bash
python tools/generate_mcp_gateway_config.py --gateway-url https://YOUR-GATEWAY-URL --region us-east-1
python tools/mcp_health_check.py --config .mcp.gateway.json
```

4. Cut over only when all MCP servers are green: copy `.mcp.gateway.json` → `.mcp.json`.

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
