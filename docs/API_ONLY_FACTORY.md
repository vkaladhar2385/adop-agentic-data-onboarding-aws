# API-only factory — Harness provision (Option B)

**Goal:** Provision a **pre-onboarded** workload and run the full pipeline **from AWS** after the client types **APPROVE** in Harness chat. No `terraform apply`, no `deploy_workload.py`, and no Cursor on the deploy path.

**Demo workload:** `supplier_lead_times`  
**Typical runtime:** ~12–15 minutes (CodeBuild resync + Step Functions E2E)  
**Status:** Green in sandbox (Harness → `trigger_provision` → factory SFN → CodeBuild → workload pipeline **SUCCEEDED**).

**Related:** architecture and components → [`FACTORY_PROVISION_DESIGN.md`](FACTORY_PROVISION_DESIGN.md) · Harness setup → [`MODE_C1_HARNESS.md`](MODE_C1_HARNESS.md) · laptop demo → [`CLIENT_DEMO_RUNBOOK.md`](CLIENT_DEMO_RUNBOOK.md) Act 6.

---

## What the client sees

```text
Presenter / client chat (Harness)
  → User confirms workload + bucket
  → User types APPROVE
  → Agent calls factory.trigger_provision
  → AWS runs adop_factory_provision (Validate → CodeBuild → E2E pipeline)
  → User asks for status → agent calls get_provision_status
  → SUCCEEDED (all three stages green)
```

**v1 entry point:** `python tools/invoke_agentcore_harness.py` (CLI wrapper around the Harness API). A future API Gateway can sit in front of the same Harness without changing the factory flow.

---

## One-time setup (operator, before first demo)

Run once per sandbox account (or after factory module changes).

| # | Task | Command |
|---|------|---------|
| 1 | AWS login | `aws login --profile aws-agent` |
| 2 | Gateway + **factory** target | `python tools/deploy_mcp_gateway.py --profile aws-agent` |
| 3 | Harness (Claude Sonnet 4.6) | `python tools/deploy_agentcore_harness.py --profile aws-agent` |
| 4 | Repo zip for CodeBuild | `python tools/package_factory_artifact.py --bucket adop-datalake-<account>-us-east-1 --profile aws-agent` |
| 5 | Factory module (SFN, CodeBuild, Lambdas + audit) | `python tools/deploy_factory_provision.py --profile aws-agent-terraform` |
| 6 | Smoke test | `python tools/harness_smoke_test.py --live --profile aws-agent` → **2/2 PASS** |
| 7 | **Workload pipeline** (after full destroy) | `python tools/provision_client_workload.py --workload supplier_lead_times --bucket adop-datalake-<account>-us-east-1 --aws-profile aws-agent` |

CodeBuild **resync** mode does not run Terraform — E2E needs `supplier_lead_times_pipeline` to exist (step 7). See [`PERSONAL_SANDBOX_RUNBOOK.md`](PERSONAL_SANDBOX_RUNBOOK.md) Step A1b.

After pulling audit-trail changes, re-run step 5 so the SFN gains `WriteProvisionAudit` and the audit Lambda is deployed.

**Bedrock:** Enable `us.anthropic.claude-sonnet-4-6`. Nova does **not** support Gateway tool-use in this account.

**Pre-onboarded workloads only:** `supplier_lead_times`, `product_inventory`. New workloads still use `/onboard-workflow` + specs on a laptop first.

---

## 10-minute demo script

### Before the room (2 min)

```powershell
aws sts get-caller-identity --profile aws-agent
python tools/harness_smoke_test.py --live --profile aws-agent
```

Confirm factory SFN exists:

```powershell
aws stepfunctions describe-state-machine --name adop_factory_provision --profile aws-agent --region us-east-1
```

**Talking point:** Discovery and spec authoring happen in Cursor (Acts 1–2). This act is **deploy + E2E entirely in AWS** after human approval.

---

### Step 1 — Discovery recap (1 min, optional)

Show that the workload already exists in git:

```text
workloads/supplier_lead_times/config/
workloads/supplier_lead_times/orchestration/supplier_lead_times_state_machine.json
```

No files are edited during this demo.

---

### Step 2 — Start provision (2 min)

Ask the client to confirm:

- **Workload:** `supplier_lead_times`
- **Bucket:** `adop-datalake-<account>-us-east-1` (no `s3://` prefix)
- **E2E:** yes (landing sync + workload Step Functions)

Then run (client says **APPROVE** out loud; include it in the prompt):

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Provision supplier_lead_times to bucket adop-datalake-<account>-us-east-1 with E2E. I APPROVE. Call trigger_provision with approve true."
```

**Expected response:**

- Status `STARTED`
- `provision_id` (e.g. `factory-2fce7b9f0e60`)
- `execution_arn` for `adop_factory_provision`

Save the execution ARN for Step 3.

**Talking point:** The agent will **not** call `trigger_provision` without explicit **APPROVE** (Harness system prompt + tool validation).

---

### Step 3 — Poll status (while AWS runs, ~12 min)

Option A — Harness (recommended for demo narrative):

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Check provision status for execution arn:<paste-execution-arn>. Call get_provision_status and summarize."
```

Option B — AWS CLI (presenter backup):

```powershell
aws stepfunctions describe-execution --execution-arn "<execution-arn>" --profile aws-agent --region us-east-1
```

**While waiting, show in console (optional):**

- Step Functions → `adop_factory_provision` → running execution
- CodeBuild → `adop-factory-dev` → latest build
- Step Functions → `supplier_lead_times_pipeline` → E2E execution

---

### Step 4 — Success criteria (2 min)

Harness `get_provision_status` (or SFN describe) should show **SUCCEEDED** for:

| Stage | Resource |
|-------|----------|
| Factory orchestration | `adop_factory_provision` |
| Deploy sync | CodeBuild project `adop-factory-dev` |
| Pipeline E2E | `supplier_lead_times_pipeline` |

Optional Athena spot-check (if catalog registered):

```sql
SELECT COUNT(*) FROM supplier_lead_times_db.silver_supplier_lead_times;
```

**Audit trail** — after success, confirm JSON on S3 (replace `factory-…` with `provision_id` from Harness):

```powershell
aws s3 cp s3://adop-datalake-<account>-us-east-1/provision-runs/factory-<id>.json - --profile aws-agent
```

Or list recent runs:

```powershell
aws s3 ls s3://adop-datalake-<account>-us-east-1/provision-runs/ --profile aws-agent
```

**Closing line:** *The client approved in chat; AWS ran validate, deploy sync, and the full medallion pipeline — no laptop deploy command.*

---

## Second workload (repeatability, +15 min)

Same flow with `product_inventory`:

```powershell
python tools/invoke_agentcore_harness.py --profile aws-agent --prompt "Provision product_inventory to bucket adop-datalake-<account>-us-east-1 with E2E. I APPROVE."
```

---

## Operator fallback (debugging only)

Bypass Harness to test the factory path directly (same SFN the Gateway tool calls):

```powershell
python tools/start_provision_api.py `
  --workload supplier_lead_times `
  --bucket adop-datalake-<account>-us-east-1 `
  --approve `
  --profile aws-agent
```

Validate payload without starting SFN:

```powershell
python tools/start_provision_api.py --workload supplier_lead_times --bucket adop-datalake-<account>-us-east-1 --approve --dry-run
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Harness does not call `trigger_provision` | Redeploy Harness: `python tools/deploy_agentcore_harness.py --profile aws-agent`. Confirm prompt includes **APPROVE**. |
| `harness_smoke_test.py --live` fails | Check Bedrock model access; use Claude Sonnet 4.6 in `config/agentcore/harness.yaml`. |
| `approve: false` or missing APPROVE | Tool returns validation error — by design. |
| CodeBuild fails on DOWNLOAD_SOURCE | Re-upload repo zip: `python tools/package_factory_artifact.py --bucket ...` |
| Factory SFN fails at E2E | See `docs/PILOT_FAILURES_AND_FIXES.md`; check CloudWatch for `adop-factory-dev-e2e` Lambda. |
| Windows `UnicodeEncodeError` on invoke | Fixed in `invoke_agentcore_harness.py`; pull latest or redirect output: `... \| Out-File -Encoding utf8 status.txt` |
| `ExpiredToken` | `aws login --profile aws-agent` |

---

## Not in v1 (optional later)

| Feature | Notes |
|---------|--------|
| Client spec upload (`s3://.../client-specs/`) | Workloads must exist in repo first |
| CodeBuild **full** terraform mode | Needs Lake Formation grants on CodeBuild role |
| Failed-run audit JSON | Success path only; failures rely on SFN/CodeBuild logs |
| OAuth / API Gateway front door | Harness invoke CLI is sufficient for demo |

---

## Teardown

After demo (personal account — stop all spend):

```powershell
python tools/destroy_sandbox.py --yes --profile aws-agent
```

Includes factory SFN, CodeBuild, and factory Lambdas. Full personal-account guide → [`PERSONAL_SANDBOX_RUNBOOK.md`](PERSONAL_SANDBOX_RUNBOOK.md).

---

## Quick reference

| Item | Value |
|------|--------|
| Factory SFN | `adop_factory_provision` |
| CodeBuild | `adop-factory-dev` |
| Gateway tools | `trigger_provision`, `get_provision_status` |
| Harness agent | `adop_onboarding_agent` (see `build/agentcore/harness.json`) |
| Unit tests | `pytest tests/test_factory_provision.py -v` |
