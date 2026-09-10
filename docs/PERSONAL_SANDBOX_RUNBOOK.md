# Personal sandbox runbook — demo day vs zero spend

**For:** Personal AWS account · Option B factory demo (`supplier_lead_times`) · **no idle spend**

**Replace** `<account>` with your account id (e.g. `199064440913`).  
**Bucket:** `adop-datalake-<account>-us-east-1`

Run all commands from the **repo root** in PowerShell.

---

## Cost rule (read once)

| When | What costs money |
|------|------------------|
| **During demo (~15 min)** | Glue job runs, CodeBuild minutes, Bedrock Harness tokens — typically **under ~$1** per full provision |
| **Idle after demo** | OpenSearch, Redshift, Redis if left up — **avoid** (not needed for Option B demo) |
| **Safe idle** | Empty S3 bucket, deleted compute — **~$0** |

**Personal account policy:** Run **After demo → destroy** every time. Do not leave Gateway + factory + workloads running overnight.

Set a budget alert (one-time):

```powershell
# AWS Console → Billing → Budgets → $5/month alert (email when exceeded)
```

---

## One-time setup (once per machine / account)

```powershell
aws login --profile aws-agent
aws sts get-caller-identity --profile aws-agent

# Terraform vars
copy iac\terraform\terraform.tfvars.example iac\terraform\terraform.tfvars
# Edit: account_id, data_lake_bucket, alert_email

copy iac\terraform\backend.hcl.example iac\terraform\backend.hcl
# Edit bucket/key if needed

# Create datalake bucket if it does not exist (bucket is NOT created by Terraform)
aws s3api head-bucket --bucket adop-datalake-<account>-us-east-1 --profile aws-agent
# If missing:
aws s3 mb s3://adop-datalake-<account>-us-east-1 --profile aws-agent --region us-east-1
```

Enable Bedrock model **`us.anthropic.claude-sonnet-4-6`** in the console (Harness tool-use).

---

## A. Rebuild before a demo (after a prior destroy)

**Time:** ~10–15 min operator work + ~15 min during live Harness provision (demo).

### Step A1 — AgentCore + factory engine

```powershell
aws login --profile aws-agent

python tools/deploy_mcp_gateway.py --profile aws-agent
python tools/deploy_agentcore_harness.py --profile aws-agent

python tools/package_factory_artifact.py --bucket adop-datalake-<account>-us-east-1 --profile aws-agent
python tools/deploy_factory_provision.py --profile aws-agent-terraform --init-backend

python tools/harness_smoke_test.py --live --profile aws-agent
```

**Done when:** smoke test **2/2 PASS** and factory SFN exists:

```powershell
aws stepfunctions describe-state-machine --name adop_factory_provision --profile aws-agent --region us-east-1
```

### Step A1b — Deploy workload pipeline (required for E2E)

After a full destroy, CodeBuild runs in **resync** mode (scripts + landing sync only — **no** Terraform). Harness E2E needs `supplier_lead_times_pipeline` to already exist:

```powershell
python tools/provision_client_workload.py `
  --workload supplier_lead_times `
  --bucket adop-datalake-<account>-us-east-1 `
  --aws-profile aws-agent
```

**One-time per rebuild** (~10 min). Skip only if you set CodeBuild `ADOP_FACTORY_MODE=full` (needs LF grants on CodeBuild role).

### Step A2 — Optional: laptop onboarding demo (Acts 1–2)

Only if you want to show `/onboard-workflow` in Cursor **before** the no-laptop act (specs + pytest in Cursor, then use A1b for deploy).

### Step A3 — Cursor MCP (for discovery / hybrid tools in room)

```powershell
python tools/switch_mcp_mode.py --mode hybrid --aws-profile aws-agent
# Reload Cursor → Settings → MCP
python tools/mcp_health_check.py
```

---

## B. During the demo (what to run in the room)

**Script:** [`API_ONLY_FACTORY.md`](API_ONLY_FACTORY.md) · [`CLIENT_DEMO_RUNBOOK.md`](CLIENT_DEMO_RUNBOOK.md) Act 6

### B1 — Pre-flight (2 min, before client joins)

```powershell
aws login --profile aws-agent
python tools/harness_smoke_test.py --live --profile aws-agent
```

### B2 — No-laptop provision (client narrative)

Client confirms workload + bucket, then says **APPROVE**:

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Provision supplier_lead_times to bucket adop-datalake-<account>-us-east-1 with E2E. I APPROVE. Call trigger_provision with approve true."
```

Save **execution_arn** and **provision_id** from the response.

### B3 — While AWS runs (~12–15 min)

Poll status (good talking time):

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Check provision status for execution arn:<paste-arn>. Call get_provision_status."
```

### B4 — Show success + audit trail

```powershell
aws s3 ls s3://adop-datalake-<account>-us-east-1/provision-runs/ --profile aws-agent
aws s3 cp s3://adop-datalake-<account>-us-east-1/provision-runs/<provision_id>.json - --profile aws-agent
```

**Done when:** factory SFN, CodeBuild, and `supplier_lead_times_pipeline` all **SUCCEEDED**.

---

## C. After demo — stop all spend (always run this)

### C1 — Preview

```powershell
python tools/destroy_sandbox.py --dry-run --profile aws-agent
```

### C2 — Destroy compute + AgentCore (keeps S3 bucket)

```powershell
python tools/destroy_sandbox.py --yes --profile aws-agent
python tools/switch_mcp_mode.py --mode local
```

This removes:

- Harness, Gateway, MCP Lambdas  
- Workload pipelines (Glue jobs, SFNs, Lambdas)  
- **Factory** SFN, CodeBuild, factory Lambdas (`module.factory_provision`)  
- MCP Glue DBs / IAM (where applicable)  
- Relevant CloudWatch log groups  

This **does not** delete the S3 bucket (cheap storage; keeps terraform state + audit JSON for history).

### C3 — Optional: delete bucket too (full reset)

Only if you want **zero** S3 storage and are OK re-uploading artifacts next time:

```powershell
python tools/destroy_sandbox.py --yes --include-data --bucket adop-datalake-<account>-us-east-1 --profile aws-agent
```

**Warning:** Deletes terraform remote state, factory repo zip, landing data, and `provision-runs/` audit files. Next rebuild needs `package_factory_artifact` + `deploy_factory_provision --init-backend` again.

### C4 — Verify nothing expensive remains

```powershell
python tools/destroy_sandbox.py --dry-run --skip-terraform --skip-agentcore --profile aws-agent
```

Check console manually if unsure:

- **Step Functions** — no `adop_*` or `supplier_lead_times_*` state machines  
- **CodeBuild** — no `adop-factory-dev`  
- **Lambda** — no `adop-*` functions  
- **OpenSearch / Redshift / ElastiCache** — none (do not deploy extensions for personal demo)

**KMS keys** from MCP workloads may sit in a **7-day pending deletion** window (AWS minimum; pennies at most).

---

## D. Quick reference card

| Phase | Command |
|-------|---------|
| **Login** | `aws login --profile aws-agent` |
| **Rebuild** | A1 block above |
| **Demo trigger** | `invoke_agentcore_harness.py` + APPROVE prompt |
| **Demo poll** | `get_provision_status` prompt |
| **Stop spend** | `destroy_sandbox.py --yes` |
| **Full nuke** | `destroy_sandbox.py --yes --include-data` |

---

## E. What NOT to deploy (personal account)

| Asset | Why skip |
|-------|------------|
| `advisory_transactions` OpenSearch / Redshift / Redis | Hourly cost; not needed for Option B |
| MWAA | Always-on cost |
| Leaving factory + workloads up overnight | Avoidable; run **C2** after demo |

---

## F. Troubleshooting

| Problem | Fix |
|---------|-----|
| `ExpiredToken` during long destroy | Use **AWS CLI v2** for login (v1 does not support `aws login`): `& "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" login --profile aws-agent` |
| Destroy stopped mid-run | Re-login, then `python tools/destroy_sandbox.py --yes --profile aws-agent` (or `--skip-terraform` for MCP/LF stragglers only) |
| Stale `build/agentcore/harness.json` after manual delete | Safe to delete; redeploy recreates via `deploy_agentcore_harness.py` |
| Gateway delete "has targets associated" | Re-run destroy (targets are deleted first; latest script waits for target removal) |
| Harness tool-use fails | Claude Sonnet 4.6 enabled; redeploy harness |
| Destroy warnings / stragglers | Re-run `destroy_sandbox.py --yes`; check console for `adop-*` |
| Factory not destroyed | Pull latest repo (factory in terraform targets); `terraform destroy -target=module.factory_provision` |
| Re-demo next week | Run **Section A** then **Section B** |

---

## Related docs

| Doc | Use |
|-----|-----|
| [`API_ONLY_FACTORY.md`](API_ONLY_FACTORY.md) | Harness-only provision script |
| [`CLIENT_DEMO_RUNBOOK.md`](CLIENT_DEMO_RUNBOOK.md) | Full client Acts 1–6 |
| [`SANDBOX_LIFECYCLE.md`](SANDBOX_LIFECYCLE.md) | Destroy flags and tag contract |
| [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) | Extension cost details (advisory_transactions) |
