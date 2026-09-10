# Client demo runbook — laptop + API factory (M1–M2)

Use this script for a **live client demo** of the ADOP Track A agent factory: discovery →
specs → render → deploy → E2E pipeline on AWS. Default demo workload:
**`supplier_lead_times`** (catalog-only, Step Functions, no OpenSearch/Redshift).

**Prerequisites:** AWS profile `aws-agent` (or your sandbox profile), Cursor with MCP
loaded, ~$2–5 sandbox spend for one deploy + one pipeline run.

**Related:** timing/cost/keep-vs-destroy → `docs/DEMO_RUNBOOK.md` · full sandbox up/down →
`docs/SANDBOX_LIFECYCLE.md` · Gateway hybrid → `docs/MODE_B_SETUP.md` · Harness API →
`docs/MODE_C1_HARNESS.md` · **no-laptop provision** → `docs/API_ONLY_FACTORY.md`.

---

## Before the room (15 min)

| Step | Command / action |
|------|------------------|
| 1 | `aws sts get-caller-identity --profile aws-agent` — confirm account |
| 2 | `python tools/mcp_health_check.py` — 13 local MCP servers green |
| 3 | Optional Mode B: `python tools/switch_mcp_mode.py --mode hybrid` then **reload Cursor MCP** |
| 4 | `cd iac/terraform && terraform init` — after any new `workloads_*.tf` |
| 5 | Confirm data-lake bucket exists: `aws s3api head-bucket --bucket adop-datalake-<account>-us-east-1` |

---

## Demo narrative (30 min)

### Act 1 — Factory onboarding (10 min)

1. In Cursor chat, run **`/onboard-workflow`** (or paste from `.cursor/commands/onboard-workflow.md`).
2. Walk through **Phase 1 discovery** with the client: zone, PK/dedup, PII, quality thresholds, schedule.
3. Show **auto-profile** on `demo/sample_data/supplier_lead_times.csv` (or their sample).
4. Sub-agents produce YAML under `workloads/<name>/config/` — **no hand-edited Glue scripts**.
5. Run locally:

```powershell
python tools/render_workload.py --workload supplier_lead_times --all --check-drift
python -m pytest workloads/supplier_lead_times/tests/ -v
```

**Talking point:** Specs are the contract; Python and Step Functions JSON are **generated**.

### Act 2 — Deploy (10 min)

One command (after human approval in chat). **M2 wrapper** (same behavior, client-friendly name):

```powershell
python tools/provision_client_workload.py `
  --workload supplier_lead_times `
  --bucket adop-datalake-<account>-us-east-1 `
  --aws-profile aws-agent
```

Equivalent low-level command:

```powershell
python tools/deploy_workload.py `
  --workload supplier_lead_times `
  --bucket adop-datalake-<account>-us-east-1 `
  --auto-provision `
  --aws-profile aws-agent
```

What `--auto-provision` does:

- Ensures `iac/terraform/workloads_<name>.tf`
- Validates configs + Cedar + compute routing
- `package_and_sync.py` → S3 (Glue scripts + Lambda zips)
- `terraform apply` → Glue jobs, Lambdas, Step Functions, EventBridge, SNS
- Uploads landing CSV → starts SFN → polls to **SUCCEEDED**

**Talking point:** Terraform is fallback; catalog/KMS/IAM/LF can be MCP-first (`docs/MCP_GUARDRAILS.md`).

### Act 3 — Verify (5 min)

```powershell
aws stepfunctions list-executions `
  --state-machine-arn <arn-from-trace> `
  --max-results 1 --profile aws-agent

aws glue get-job-runs --job-name supplier_lead_times_ingest_bronze --max-results 1 --profile aws-agent
```

Optional Athena spot-check (after catalog registration):

```sql
SELECT COUNT(*) FROM supplier_lead_times_db.silver_supplier_lead_times;
```

### Act 4 — Dual route: API / no-laptop (10 min, M2)

**Before demo:** refresh AWS login (`aws login --profile aws-agent`), deploy Gateway, hybrid MCP:

```powershell
python tools/deploy_mcp_gateway.py --profile aws-agent
python tools/switch_mcp_mode.py --mode hybrid
# Reload Cursor MCP
```

**Harness smoke** (config check, no AWS):

```powershell
python tools/harness_smoke_test.py
python tools/harness_smoke_test.py --live --profile aws-agent
```

**Live API prompts** (same agent, no Cursor):

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "List Glue databases in this account"
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "What Phase 1 questions for a HIPAA weekly CSV pipeline?"
```

See `docs/MODE_B_SETUP.md` and `docs/MODE_C1_HARNESS.md`.

### Act 5 — Second workload proof (5 min, M2)

Show factory repeatability with **`product_inventory`** (already onboarded):

```powershell
python tools/provision_client_workload.py --workload product_inventory --bucket adop-datalake-<account>-us-east-1 --dry-run
python tools/provision_client_workload.py --workload product_inventory --bucket adop-datalake-<account>-us-east-1 --aws-profile aws-agent
```

**Talking point:** Same factory, different domain — no hand-edited Glue scripts.

### Act 6 — No-laptop provision (15 min, Option B)

**Prerequisite:** Factory module applied once (`tools/deploy_factory_provision.py`) and Harness smoke **2/2 PASS**. Full script → [`docs/API_ONLY_FACTORY.md`](API_ONLY_FACTORY.md).

**Narrative:** Client approves in Harness chat; **AWS** runs validate → CodeBuild sync → workload Step Functions E2E. No `provision_client_workload.py` on the demo path.

1. **Confirm factory is up (operator, 1 min):**

```powershell
python tools/harness_smoke_test.py --live --profile aws-agent
aws stepfunctions describe-state-machine --name adop_factory_provision --profile aws-agent --region us-east-1
```

2. **Client confirms** workload `supplier_lead_times`, bucket `adop-datalake-<account>-us-east-1`, E2E yes — then says **APPROVE**.

3. **Trigger provision (Harness):**

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Provision supplier_lead_times to bucket adop-datalake-<account>-us-east-1 with E2E. I APPROVE. Call trigger_provision with approve true."
```

4. **Poll (~12–15 min)** — save `execution_arn` from the response:

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Check provision status for execution arn:<paste-arn>. Call get_provision_status."
```

5. **Done when** all three stages show **SUCCEEDED**: factory SFN, CodeBuild `adop-factory-dev`, workload SFN `supplier_lead_times_pipeline`.

**Talking point:** Same approval gate as laptop deploy, but the **runner lives in AWS** (Step Functions + CodeBuild), not on the presenter's machine.

**Operator fallback (not shown to client):** `python tools/start_provision_api.py --workload supplier_lead_times --bucket adop-datalake-<account>-us-east-1 --approve`

---

## Troubleshooting (quick)

| Symptom | Fix |
|---------|-----|
| `InvalidAccessKeyId` on S3 upload | Pass `--aws-profile aws-agent` to `deploy_workload.py` |
| Terraform `No valid credential sources` | Use `aws login --profile aws-agent`; deploy maps to `aws-agent-terraform` (credential_process) for Terraform |
| `Module not installed` | `cd iac/terraform && terraform init` |
| `FileNotFoundError` in `package_and_sync` | Extension Lambdas skipped automatically; ensure `register_catalog.py` exists |
| SFN fails at PostDeploymentVerify | LF grants / MCP catalog — see `docs/PILOT_FAILURES_AND_FIXES.md` |
| Harness tool-use / model error | Enable **Anthropic** in Bedrock; use `us.anthropic.claude-sonnet-4-6` in `config/agentcore/harness.yaml` (Nova fails Gateway ToolUse) |
| Harness provision stuck RUNNING | Poll with `get_provision_status` or `aws stepfunctions describe-execution`; E2E can take ~15 min |
| Factory CodeBuild DOWNLOAD_SOURCE fail | Re-run `python tools/package_factory_artifact.py --bucket adop-datalake-<account>-us-east-1` |
| Hybrid MCP not routing | Reload Cursor MCP after `switch_mcp_mode.py --mode hybrid` |
| **`agentcore-gateway` Error in Cursor** | Use stdio proxy: `python tools/switch_mcp_mode.py --mode gateway --aws-profile aws-agent`, then **Reload Window**. Run `python tools/verify_gateway_mcp.py` |
| `ExpiredToken` on Gateway deploy | `aws login --profile aws-agent` (AWS CLI v2) then retry |
| Gateway Lambda tag error | Fixed in `tag_lambda` (requires function ARN); pull latest |

---

## Teardown (after demo)

Same session or next day:

```powershell
cd iac/terraform
terraform destroy -target=module.supplier_lead_times -auto-approve
```

Keep the S3 bucket if re-demoing; destroy OpenSearch/Redshift only for `advisory_transactions`
(see `docs/DEMO_RUNBOOK.md`).

---

## Milestone map (15 steps)

| M | Focus | Key exit test |
|---|--------|----------------|
| **M1** (this doc) | Laptop demo + hybrid MCP + SFN E2E | Green `--auto-provision` on `supplier_lead_times` |
| **M2** | Dual route (Gateway iam/core, `provision_client_workload.py`, Harness smoke) | Second workload + API prompt path |
| **M3 (lean)** | Sandbox lifecycle + CI smoke + documented API path | Spin up / tear down sandbox; CI catches broken factory; OAuth/C2 deferred |

### M3 lean — what you use (no extra complexity)

| Piece | Command / doc | You get |
|-------|----------------|---------|
| **Spin up sandbox** | `python tools/provision_sandbox.py --bucket ...` | Gateway + optional Harness + pipeline in one go |
| **Tear down** | `python tools/destroy_sandbox.py --yes` | Stop hourly spend after demo |
| **One workload** | `python tools/provision_client_workload.py --workload ... --bucket ...` | Same as M2, client-friendly name |
| **API path (v1)** | Harness chat → **APPROVE** → `trigger_provision` in AWS | No-laptop **deploy + E2E** — see Act 6 / `docs/API_ONLY_FACTORY.md` |
| **CI safety net** | GitHub `ci.yml` factory dry-run | PR fails if specs/tests/drift break before anyone touches AWS |

**Deferred (optional later):** Harness OAuth/JWT, automatic spec upload from S3, C2 Runtime container.

See `docs/SANDBOX_LIFECYCLE.md` and `docs/STATUS.md`.

---

## M3 API demo script (5 min, no OAuth)

**Discovery-only (5 min):**

1. `python tools/harness_smoke_test.py --live --profile aws-agent`
2. `python tools/invoke_agentcore_harness.py --prompt "What Phase 1 questions for a HIPAA CSV pipeline?"`

**Full no-laptop provision (15 min):** Act 6 or [`docs/API_ONLY_FACTORY.md`](API_ONLY_FACTORY.md).

**Laptop path (Acts 1–2):** `/onboard-workflow` → specs + `provision_client_workload.py`.

**Teardown:** `python tools/destroy_sandbox.py --yes`

See `docs/STATUS.md` for factory % and Tier A/B checklist.
