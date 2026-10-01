# Pipeline from scratch → deploy → destroy — cheatsheet

**One page for you.** Replaces hunting across `DEMO_PREP_ABCD.md`, `CLIENT_DEMO_RUNBOOK.md`, and `AGENTS.md` for day-to-day commands.

**Repo root:** all commands run from `C:\Vis\MyLearning\Data-Engineering\ADOP`

**Slides (in-room):** [`presentations/demo-laptop-hybrid-deck.html`](presentations/demo-laptop-hybrid-deck.html) · **Private Q&A:** [`presentations/demo-laptop-hybrid-presenter-qa.html`](presentations/demo-laptop-hybrid-presenter-qa.html)

---

## Variables (set once per session)

```powershell
$PROFILE = "aws-agent"
$ACCOUNT = (aws sts get-caller-identity --profile $PROFILE --query Account --output text)
$BUCKET  = "adop-datalake-$ACCOUNT-us-east-1"
$WORKLOAD = "supplier_lead_times"   # new onboard: your chosen name
```

---

## Two paths — pick one

| Path | When | Time | AWS spend |
|------|------|------|-----------|
| **A — New workload** | First time onboarding a feed | Hours (discovery + build) + ~90 min deploy | ~$2–5 per E2E |
| **B — Pre-built SKU** | Demo / rehearsal (`supplier_lead_times` already in repo) | ~30 min live | ~$2–5 per E2E |

Both paths share **Phase 0**, **Deploy (Phase 5)**, **Verify**, and **Destroy**.

---

## Phase 0 — One-time / before every deploy (15 min)

```powershell
aws login --profile $PROFILE
aws sts get-caller-identity --profile $PROFILE

# Terraform (first time only)
copy iac\terraform\terraform.tfvars.example iac\terraform\terraform.tfvars
# Edit: account_id, data_lake_bucket, alert_email
cd iac\terraform; terraform init; cd ..\..

# MCP wiring (first time or after registry change)
python tools/generate_mcp_config.py
python tools/mcp_health_check.py
# Optional offline: python tools/mcp_health_check.py --skip-aws

# Optional hybrid demo (Gateway) — see ../MODE_B_SETUP.md
python tools/deploy_mcp_gateway.py --profile $PROFILE
python tools/switch_mcp_mode.py --mode hybrid --aws-profile $PROFILE
python tools/verify_gateway_mcp.py --profile $PROFILE
# Reload Cursor → Settings → MCP

# Confirm lake bucket exists
aws s3api head-bucket --bucket $BUCKET --profile $PROFILE
```

**Gate:** `mcp_health_check.py` must pass REQUIRED servers (`glue-athena`, `lakeformation`, `iam`) before deploy.

---

## Path A — New pipeline from scratch (no AWS until Phase 5)

### Phase 1 — Discovery (HITL, Cursor only)

In Cursor chat:

```
/onboard-workflow
```

**You must answer** (agent must not guess): zones, source path/format/volume, PK, dedup, transforms, PII, quality thresholds, schedule, orchestrator, sinks, compute (Shell vs Spark).

**Done when:** `workloads/{name}/.discovery_complete` exists.

**Human gates:** discovery complete → **"Ready to run dedup + build?"** → later **"Approve artifacts?"**

Reference: `.cursor/commands/onboard-workflow.md` · `AGENTS.md`

---

### Phase 2 — Dedup (agent, local)

Agent runs dedup sub-agent — checks overlapping sources in `workloads/*/config/source.yaml`.

**You decide** if OVERLAP: rename, merge, or cancel.

---

### Phase 4 — Build (local, no `terraform apply`)

Agent writes **YAML + codegen specs** under `workloads/{name}/config/`, then:

```powershell
python tools/validate_configs.py workloads/$WORKLOAD/
python tools/validate_compute.py --workload $WORKLOAD
python tools/render_workload.py --workload $WORKLOAD --all --write
python tools/render_workload.py --workload $WORKLOAD --all --check-drift
python tools/check_codegen_drift.py
python -m pytest workloads/$WORKLOAD/tests/ -v
```

**Ensure Terraform module exists** (factory default):

```powershell
python tools/ensure_terraform_module.py --workload $WORKLOAD
```

**Outputs:** `scripts/`, `orchestration/*_state_machine.json`, `sql/`, `tests/`, `iac/terraform/workloads_{name}.tf`

**Do not** hand-edit generated `.py` / SFN JSON — change spec or template, re-render.

---

## Path B — Pre-built workload (demo / rehearsal)

Discovery and build already done for `supplier_lead_times`. Skip to **local proof**, then deploy:

```powershell
python tools/render_workload.py --workload supplier_lead_times --all --check-drift
python -m pytest workloads/supplier_lead_times/tests/ -v
```

Show `workloads/supplier_lead_times/config/` + `.discovery_complete` in Cursor (Live **Part 1** in slides).

---

## Phase 5 — Deploy (AWS, human APPROVE required)

**Say in chat:** `I approve deploy`

**Dry-run first (no spend):**

```powershell
python tools/deploy_workload.py --workload $WORKLOAD --bucket $BUCKET --dry-run --aws-profile $PROFILE
```

**Full path (recommended):**

```powershell
python tools/deploy_workload.py `
  --workload $WORKLOAD `
  --bucket $BUCKET `
  --auto-provision `
  --aws-profile $PROFILE
```

`--auto-provision` = ensure TF module + validators + drift + pytest + MCP catalog/LF (if mcp-owned) + `package_and_sync` + **terraform apply** + landing CSV sync + **Step Functions E2E poll**.

**What runs where:**

| Owner | Creates |
|-------|---------|
| **MCP** | Glue DB/tables, Lake Formation, IAM/KMS (when `owner: mcp` in `compute.yaml`) |
| **Terraform** | Glue **jobs**, Lambda, Step Functions, EventBridge, SNS |

---

## Phase 6 — Verify (5 min)

```powershell
aws stepfunctions list-executions `
  --state-machine-arn <arn> `
  --max-results 1 `
  --profile $PROFILE
```

- Step Functions console: all states **Succeeded**
- Quality gates: Silver ≥ 0.80, Gold ≥ 0.95
- Optional Athena: `SELECT COUNT(*) FROM supplier_lead_times_db.silver_supplier_lead_times;`

---

## Destroy — after demo (required for $0 idle)

**Preview:**

```powershell
python tools/destroy_sandbox.py --dry-run
```

**Destroy compute + Gateway + MCP infra:**

```powershell
python tools/destroy_sandbox.py --yes
```

**Also delete lake data (optional, full cleanup):**

```powershell
python tools/destroy_sandbox.py --yes --include-data --bucket $BUCKET
```

**Reset Cursor MCP to local:**

```powershell
python tools/switch_mcp_mode.py --mode local
```

**Single-workload only** (alternative to full sandbox destroy):

```powershell
cd iac\terraform
terraform destroy -target=module.supplier_lead_times -auto-approve
cd ..\..
```

Details: [`../SANDBOX_LIFECYCLE.md`](../SANDBOX_LIFECYCLE.md) · extension cost: [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md)

---

## End-to-end checklist (printable)

```
[ ] Phase 0   aws login · terraform init · mcp_health_check · bucket exists
[ ] Path A    /onboard-workflow · .discovery_complete · render · pytest · ensure_terraform_module
      OR
[ ] Path B    check-drift · pytest (supplier_lead_times)
[ ] Deploy    dry-run OK · said "I approve deploy" · --auto-provision green
[ ] Verify    SFN Succeeded · optional Athena count
[ ] Destroy   destroy_sandbox.py --yes · switch_mcp_mode local
```

---

## Human-in-the-loop (never skip)

| Gate | You say / do |
|------|----------------|
| Discovery | Answer all Phase 1 questions before codegen |
| Build | **"Ready to run dedup + build?"** / **"Approve artifacts?"** |
| Deploy | **"I approve deploy"** before any `--approve-apply` or `--auto-provision` |
| Teardown | Confirm `destroy_sandbox.py` when demo is done |

---

## Troubleshooting (top 5)

| Symptom | Fix |
|---------|-----|
| Expired AWS token | `aws login --profile aws-agent` |
| MCP health fail | `python tools/generate_mcp_config.py` · reload Cursor MCP |
| Terraform no credentials | Deploy uses `aws-agent` → maps to `aws-agent-terraform` for TF |
| `terraform_sync pending` | `python tools/ensure_terraform_module.py --workload $WORKLOAD` |
| SFN / Glue fail | CloudWatch logs · [`../PILOT_FAILURES_AND_FIXES.md`](../PILOT_FAILURES_AND_FIXES.md) |

Full table: [`CLIENT_DEMO_RUNBOOK.md`](CLIENT_DEMO_RUNBOOK.md) § Troubleshooting

---

## Related docs (by role)

| Doc | Use when |
|-----|----------|
| **This cheatsheet** | Commands start → finish |
| `CLIENT_DEMO_RUNBOOK.md` | Demo day narrative + more troubleshooting |
| `DEMO_PREP_ABCD.md` | Multi-day prep (quiz, file trace, dry run) |
| `FACTORY_LEARNING_GUIDE.md` | Learn concepts before first demo |
| `AGENTS.md` | Agent contract / phase gates |
| [`../MCP_GUARDRAILS.md`](../MCP_GUARDRAILS.md) | Deploy ownership detail |

**Cursor skills:** No ADOP-specific skill in `.cursor/skills` — use this file + `/onboard-workflow` command instead.
