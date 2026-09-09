# Deploy Agent — validate, sync, plan (apply only with approval)

You are a **sub-agent** or **main agent in Phase 5**. You may use **AWS CLI** and **Terraform**
only when the user has explicitly approved deploy.

When finishing as a sub-agent, return **AgentOutput JSON**
(`prompts/onboarding/_agent_output_contract.md`) with `agent_type`: `"devops"`.

Read `TOOL_ROUTING.md` and `docs/MCP_GUARDRAILS.md` — MCP-first catalog/LF/verify; Terraform fallback for jobs/SFN.

## Preconditions

- [ ] Phase 1 `.discovery_complete` exists
- [ ] `pytest workloads/{name}/tests/ -v` passed
- [ ] `validate_configs.py` and `validate_compute.py` passed
- [ ] `python tools/check_codegen_drift.py` passed
- [ ] User said **deploy** / **apply** / **push to AWS**

## Steps (in order)

### 1. Pre-flight

```bash
aws sts get-caller-identity
python tools/validate_configs.py workloads/{name}/
python tools/validate_compute.py --workload {name}
python -m pytest workloads/{name}/tests/ -v
```

### 2. Package and sync

```bash
python tools/deploy_workload.py --workload {name} --dry-run
python tools/deploy_workload.py --workload {name} --bucket {lake_bucket}
```

Dry-run is files-only. The default live path runs `package_and_sync.py` and `terraform plan`.

### 3. Apply (human gate)

**Stop** after plan unless `--approve-apply` was passed with explicit user consent:

```bash
python tools/deploy_workload.py --workload {name} --bucket {lake_bucket} --approve-apply
```

Never run `terraform apply` without the user typing approval in chat.

### 4. Zero-manual provision (recommended for new workloads)

One command after user approves deploy — Terraform module, landing data, apply, SFN start + poll:

```bash
python tools/deploy_workload.py --workload {name} --bucket {lake_bucket} --auto-provision
```

Equivalent flags: `--ensure-tf-module --approve-apply --sync-landing --run-e2e`

Granular tools (sub-agent steps):

| Step | Tool |
|---|---|
| Generate `iac/terraform/workloads_{name}.tf` | `python tools/ensure_terraform_module.py --workload {name}` |
| Upload demo CSV to landing | `python tools/sync_landing_data.py --workload {name} --bucket {lake_bucket}` |
| Start SFN + poll | `python tools/run_e2e_pipeline.py --workload {name} --bucket {lake_bucket}` |

Record execution ARN from stdout / `workloads/{name}/logs/trace_events.jsonl` in `docs/STATUS.md`.

## Terraform notes (Track A)

- New workloads: auto-generate `iac/terraform/workloads_{name}.tf` via `ensure_terraform_module.py` (do not hand-edit).
- `glue_jobs` must match `config/compute.yaml`.
- Extension modules (Redshift, OpenSearch, Redis) are optional per workload.

## On failure

- Do not declare success if verifier fails.
- Point user to `docs/PILOT_FAILURES_AND_FIXES.md`.
- Log phase to `workloads/{name}/logs/trace_events.jsonl`.
