# MCP_GUARDRAILS.md — Track A (MCP-first, Terraform fallback)

Track A deploy policy: **MCP creates what the official 13 servers can**; **Terraform is
fallback** for compute, orchestration, and extensions. This is a subset of official ADOP
Phase 5 — adapted for Step Functions (not MWAA).

Official reference: `../agentic-projects/ADOP/MCP_GUARDRAILS.md`  
Server registry: `../agentic-projects/ADOP/tool-registry/servers.yaml`

---

## Phase 0 — MCP health check (mandatory before Phase 5)

Re-run before any deploy. Do **not** proceed if any **REQUIRED** server fails.

```bash
python tools/mcp_health_check.py
```

| Tier | Servers |
|---|---|
| **REQUIRED** | `glue-athena`, `lakeformation`, `iam` |
| **WARN** | `cloudtrail`, `redshift`, `core`, `s3-tables`, `pii-detection` |
| **OPTIONAL** | `sagemaker-catalog`, `lambda`, `cloudwatch`, `cost-explorer`, `dynamodb` |

Present health results to the human before deploy.

**Gateway mode:** after `deploy_mcp_gateway.py`, health may run against `.mcp.gateway.json`
via `verify_gateway_mcp.py`. **Factory provision** requires human `APPROVE` in Harness before
`factory.trigger_provision` — see `docs/FACTORY_PROVISION_DESIGN.md`.

---

## Phase 5 — Deploy (main agent only, human approved)

### Step 5.0 — Preconditions

- [ ] `.discovery_complete` exists
- [ ] `pytest workloads/{name}/tests/ -v` passed
- [ ] `validate_configs.py` + `validate_compute.py` passed
- [ ] `python tools/check_codegen_drift.py` passed
- [ ] User explicitly approved deploy

### Step 5.1 — Terraform fallback (compute + orchestration)

Run **first** for assets Terraform owns:

```bash
python tools/deploy_workload.py --workload {name} --dry-run
python tools/deploy_workload.py --workload {name} --bucket {lake_bucket}
# apply only with --approve-apply + user consent
```

Creates/updates: Glue **jobs**, Lambda functions, Step Functions, EventBridge, SNS, IAM roles
**only if still in `.tf`**. Do not MCP-create the same resources in the same session.

### Step 5.2 — MCP catalog (Glue database + tables)

| Operation | MCP tool | Fallback |
|---|---|---|
| Create database | `glue-athena` `create_database` | `aws glue create-database` |
| Create / update table | `glue-athena` `create_table` / `update_table` | `aws glue create-table` |
| Verify table | `glue-athena` `get_table` | CLI |

**Rule:** If Terraform or `register_catalog` Lambda already owns a table, do not MCP-recreate
it — use MCP for **tags and grants** only until TF resources are removed from state.

### Step 5.3 — MCP Lake Formation

| Operation | MCP tool | Fallback |
|---|---|---|
| Create LF tag | `lakeformation` `create_lf_tag` | CLI |
| Tag resource | `lakeformation` `add_lf_tags_to_resource` | CLI |
| Grant permissions | `lakeformation` `grant_permissions` | CLI / Lambda grant tools |

Align with `semantic.yaml` PII columns from Phase 1.

### Step 5.4 — MCP verify + audit

| Operation | MCP tool |
|---|---|
| Athena sample query | `glue-athena` `athena_query` |
| Redshift Spectrum check | `redshift` `execute_query` |
| Audit PutObject / CreateTable | `cloudtrail` `lookup_events` |

### Step 5.5 — Step Functions (CLI, not MCP)

Official 13 has **no** Step Functions MCP. After TF apply + MCP catalog:

```bash
aws stepfunctions start-execution --state-machine-arn ... --input file://...
```

Wait for `PostDeploymentVerify` in the state machine.

---

## Guardrail rules

1. **One owner per ARN** — MCP or Terraform, never both for the same resource type in one deploy.
2. **MCP-first for data plane** — catalog, LF, S3 data uploads, verify queries.
3. **TF fallback for control plane** — Glue jobs, SFN, EventBridge, Lambdas, extension modules.
4. **No auto-retry on MCP failure** — report step, tool, error; ask human.
5. **Sub-agents never use MCP** — build phases are file-only.

---

## Cutover note (existing sandbox)

Resources already in Terraform state must be **removed from `.tf` and state** before MCP
becomes their owner. Do not MCP-create tables/jobs that `terraform plan` still manages.

Recommended first cutover slice: **Glue catalog + LF only**, keeping jobs/SFN in Terraform.

**Done for `advisory_transactions`:** `catalog_owner = "mcp"` in Terraform; database via
`tools/mcp_deploy_catalog.py`. Runbook: `docs/MCP_CUTOVER.md`.

---

## Related docs

| Doc | Purpose |
|---|---|
| `TOOL_ROUTING.md` | Phase → tool map, ownership table |
| `docs/MCP_CUTOVER.md` | advisory_transactions state rm + deploy order |
| `docs/TRACK_B.md` | Official ADOP comparison |
| `docs/PILOT_FAILURES_AND_FIXES.md` | Sandbox lessons |
