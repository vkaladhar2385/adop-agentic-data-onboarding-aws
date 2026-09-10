# Client demo runbook — 30-minute laptop factory (Milestone 1)

Use this script for a **live client demo** of the ADOP Track A agent factory: discovery →
specs → render → deploy → E2E pipeline on AWS. Default demo workload:
**`supplier_lead_times`** (catalog-only, Step Functions, no OpenSearch/Redshift).

**Prerequisites:** AWS profile `aws-agent` (or your sandbox profile), Cursor with MCP
loaded, ~$2–5 sandbox spend for one deploy + one pipeline run.

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

One command (after human approval in chat):

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

### Act 4 — Mode B / API teaser (5 min, optional)

- **Gateway:** `python tools/deploy_mcp_gateway.py --profile aws-agent` (2 targets live; 13 planned M2)
- **Harness (API route):** `python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "List Glue databases"`
- Show `docs/MODE_B_SETUP.md` and `docs/MODE_C1_HARNESS.md` for no-laptop path (Milestone 2)

---

## Troubleshooting (quick)

| Symptom | Fix |
|---------|-----|
| `InvalidAccessKeyId` on S3 upload | Pass `--aws-profile aws-agent` to `deploy_workload.py` |
| Terraform `No valid credential sources` | Use `aws login --profile aws-agent`; deploy maps to `aws-agent-terraform` (credential_process) for Terraform |
| `Module not installed` | `cd iac/terraform && terraform init` |
| `FileNotFoundError` in `package_and_sync` | Extension Lambdas skipped automatically; ensure `register_catalog.py` exists |
| SFN fails at PostDeploymentVerify | LF grants / MCP catalog — see `docs/PILOT_FAILURES_AND_FIXES.md` |
| Harness Marketplace / model error | Enable Anthropic in Bedrock console, or use `us.amazon.nova-pro-v1:0` in `config/agentcore/harness.yaml` |
| Hybrid MCP not routing | Reload Cursor MCP after `switch_mcp_mode.py --mode hybrid` |

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
| **M3** | Production consulting (OAuth, per-client sandbox, CI smoke, C2 Runtime) | Client self-serve spec → pipeline |

See `docs/STATUS.md` for factory % and Tier A/B checklist.
