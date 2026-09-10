# Sandbox lifecycle — provision and destroy from your laptop

One-command create/teardown for ADOP AWS assets. Run all commands from the **repo root**.

## Tag contract

All sandbox resources are tagged from **`config/sandbox_tags.yaml`**:

| Tag | Value |
|-----|-------|
| `Project` | `adop` |
| `ManagedBy` | `adop-sandbox` |
| `Environment` | `sandbox` |

**Create:** `deploy_mcp_gateway`, `mcp_deploy_infrastructure`, and Terraform read this manifest.  
**Destroy:** `destroy_sandbox.py` scans by tag (Resource Groups API) **and** falls back to `adop-*` name prefixes for legacy resources.

Glue databases store `adop:managed=true` in Parameters (Glue has no native DB tags).

---

## Prerequisites

```powershell
aws login --profile aws-agent
aws sts get-caller-identity --profile aws-agent

# One-time Terraform setup
copy iac\terraform\terraform.tfvars.example iac\terraform\terraform.tfvars
# Edit account_id, data_lake_bucket, alert_email
cd iac\terraform
terraform init
cd ..\..
```

Terraform apply/destroy uses profile **`aws-agent-terraform`** (credential_process), same as `deploy_workload.py`.

---

## Provision everything

```powershell
# Full sandbox: Gateway (13 MCP targets) + Harness + advisory_transactions pipeline
python tools/provision_sandbox.py --bucket adop-datalake-YOUR_ACCOUNT-us-east-1

# Gateway only (no Harness, no Terraform workloads)
python tools/provision_sandbox.py --gateway-only --bucket adop-datalake-YOUR_ACCOUNT-us-east-1

# Multiple workloads
python tools/provision_sandbox.py --bucket ... --workloads advisory_transactions,supplier_lead_times

# Preview steps only
python tools/provision_sandbox.py --dry-run --bucket ...
```

After provision, reload **Cursor → Settings → MCP**.

---

## Destroy everything

```powershell
# 1. Preview (safe)
python tools/destroy_sandbox.py --dry-run

# 2. Destroy AgentCore + Terraform + MCP infra
python tools/destroy_sandbox.py --yes

# 3. Also delete S3 datalake bucket and all objects
python tools/destroy_sandbox.py --yes --include-data --bucket adop-datalake-YOUR_ACCOUNT-us-east-1

# 4. Point Cursor back to local stdio MCP
python tools/switch_mcp_mode.py --mode local
```

### Destroy order (automatic)

1. AgentCore Harness  
2. AgentCore Gateway (targets, then gateway)  
3. MCP Lambda functions (`adop-mcp-*`)  
4. AgentCore IAM roles  
5. Terraform destroy (pipelines, budget; targeted retry if full destroy fails)  
6. Lake Formation grant revocation (`revoke_lf_grants`)  
7. MCP-owned Glue DB, KMS (schedule deletion), workload IAM roles  
8. Optional: empty + delete S3 bucket (`--include-data`)  
9. CloudWatch log groups (`/aws/bedrock*`, `/aws/lambda/adop-*`)  
10. Disable Bedrock model invocation logging (default on)  
11. Verify by tag scan + name prefix for stragglers  

### Partial destroy

```powershell
python tools/destroy_sandbox.py --yes --skip-terraform      # AgentCore only
python tools/destroy_sandbox.py --yes --skip-agentcore      # Pipelines + MCP infra only
python tools/destroy_sandbox.py --yes --no-extensions       # Skip OpenSearch/Redshift/Redis
```

---

## What “zero resources” means

| Resource | After destroy |
|----------|----------------|
| Lambda, SFN, Glue jobs, Gateway, Harness | **Gone** |
| IAM roles (ADOP-prefixed) | **Gone** (if not shared) |
| S3 bucket | **Gone** only with `--include-data` |
| KMS CMKs (MCP-owned) | **Pending deletion 7 days** — AWS minimum |
| Bedrock logging config | May remain; disable in console if needed |
| `agentic-adop` Bedrock role | Not deleted by default (may be shared) |

---

## Cost while resources exist

Idle AgentCore Gateway + Lambdas cost very little; **Bedrock Harness invocations** and **OpenSearch/Redshift** (if extensions applied) cost more. Use `destroy_sandbox.py --yes` when done demoing.

---

## Files

| File | Role |
|------|------|
| `config/sandbox_tags.yaml` | Canonical tags (create + destroy) |
| `shared/deploy/sandbox_tags.py` | Tag helpers + Resource Groups scan |
| `tools/provision_sandbox.py` | CLI — create sandbox |
| `tools/destroy_sandbox.py` | CLI — tear down sandbox |
| `shared/deploy/sandbox_lifecycle.py` | Shared orchestration logic |
| `shared/deploy/mcp_lf.py` | `revoke_lf_grants()` on destroy |
| `shared/deploy/bedrock_logging.py` | Disable invocation logging on destroy |
