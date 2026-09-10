# MCP cutover — advisory_transactions (MCP-first data plane)

**MCP owns:** Glue catalog database, zone KMS keys, pipeline IAM roles, Lake Formation grants.  
**Terraform owns:** Glue jobs, Lambdas, Step Functions, EventBridge Scheduler, SNS, extensions, Budget.

| Asset | Owner |
|---|---|
| Glue database `advisory_transactions_db` | **MCP** (`tools/mcp_deploy_infrastructure.py`) |
| KMS keys (bronze/silver/gold) | **MCP** |
| IAM (Glue, Lambda, SFN, Scheduler roles) | **MCP** |
| LF grants (Glue/Lambda principals) | **MCP** |
| Glue tables (Iceberg) | **Glue ETL jobs** (Spark commit at runtime) |
| LF-Tags on PII columns | **register_catalog Lambda** in SFN |
| Glue jobs, SFN, EventBridge, Lambdas, SNS | **Terraform** |

Config: `workloads/advisory_transactions/config/compute.yaml` → `catalog.owner: mcp`  
Terraform: `iac/terraform/main.tf` → `catalog_owner = "mcp"`

**Contrast:** `supplier_lead_times` and other factory workloads may use `catalog.owner: terraform`
(default) — MCP still runs Phase 5 verify; Terraform creates the Glue database. See each
workload's `config/compute.yaml`.

---

## Fresh sandbox (after terraform destroy)

No `terraform state rm` needed. MCP creates data-plane resources first; Terraform
creates compute/orchestration only.

## One-time migration (existing sandbox with old Terraform state)

If resources were previously Terraform-owned, remove them from state **before** apply
(MCP keeps the live AWS objects):

```powershell
cd C:\Vis\MyLearning\Data-Engineering\ADOP\iac\terraform
terraform init
terraform state rm 'module.advisory_transactions.aws_glue_catalog_database.db[0]'  # if present
# Repeat for KMS, IAM, LF resources if they existed in state under old ownership.
terraform plan   # must NOT destroy MCP-owned assets
```

---

## Deploy order (Phase 5)

1. Preflight + validators (unchanged):
   ```powershell
   python tools/deploy_workload.py --workload advisory_transactions --dry-run
   ```

2. MCP health + infrastructure (catalog, KMS, IAM, LF):
   ```powershell
   python tools/mcp_health_check.py
   python tools/mcp_deploy_infrastructure.py --workload advisory_transactions --bucket <lake> --dry-run
   python tools/mcp_deploy_infrastructure.py --workload advisory_transactions --bucket <lake> --apply
   ```
   Or combined deploy (runs MCP step automatically):
   ```powershell
   python tools/deploy_workload.py --workload advisory_transactions --bucket <lake>
   ```

3. Terraform (jobs, SFN, Lambdas, SNS — not MCP-owned data plane):
   ```powershell
   python tools/deploy_workload.py --workload advisory_transactions --bucket <lake> --approve-apply
   ```
   Or plan-only first without `--approve-apply`.

4. Run pipeline (SFN). Iceberg jobs register Silver/Gold tables.

5. LF-Tags (if not only via SFN RegisterCatalog):
   ```powershell
   python tools/mcp_deploy_catalog.py --workload advisory_transactions --apply-lf-tags
   ```

Dry-run anytime:
```powershell
python tools/mcp_deploy_catalog.py --workload advisory_transactions --dry-run
```

---

## With live MCP (Claude Code / Cursor)

Replace step 2 with MCP tools when connected:

| Step | MCP tool |
|---|---|
| Create database | `glue-athena` → `create_database` |
| Verify | `glue-athena` → `get_database` |
| LF-Tags | `lakeformation` → `add_lf_tags_to_resource` |

Use `tools/mcp_deploy_catalog.py` when MCP is unavailable (CI, scripts).

---

## Rollback to Terraform-owned catalog

1. Set `catalog_owner = "terraform"` in `main.tf` and `catalog.owner: terraform` in compute.yaml.
2. `terraform import module.advisory_transactions.aws_glue_catalog_database.db[0] advisory_transactions_db`
3. Apply.

---

## Next cutovers

- Move LF-Tags fully to MCP (reduce register_catalog Lambda scope)
- Add MCP tools for Glue job / SFN create to shrink Terraform further

See `docs/MCP_GUARDRAILS.md`, `TOOL_ROUTING.md`.
