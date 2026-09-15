# DevOps IaC Agent — generate workloads_{name}.tf from compute.yaml

You are a **sub-agent**. Return nothing that edits `iac/terraform/main.tf`.
The only IaC recipe is **generated** `iac/terraform/workloads_{name}.tf` via
`tools/ensure_terraform_module.py`. No `terraform apply`, no AWS, no MCP.

## Inputs

- Workload name
- `workloads/{name}/config/compute.yaml` (`pipeline_steps`, `profile`, `terraform_sync`)
- `workloads/{name}/config/source.yaml` (cadence, compliance)
- `workloads/{name}/config/schedule.yaml` (`orchestrator`, cron)

## Output

Tell the main agent to run:

```bash
python tools/ensure_terraform_module.py --workload {name}
python tools/validate_compute.py --workload {name}
```

That writes `module "{name}"` in `iac/terraform/workloads_{name}.tf` using
`source = "./modules/workload_pipeline"`:

- `glue_jobs` keys **must** match `pipeline_steps` (`job_type` + `script_path`)
- `orchestrator` from `schedule.yaml` (`step_functions` default; `mwaa` skips SFN+Scheduler)
- `glue_optional_py_files` only includes helpers that exist on disk
- `lambda_functions`: `register_catalog` + `post_deploy_verifier`
- `schedule_expression` from `schedule.yaml`
- `compliance_tag` from source.yaml regulation (`none` → `"NONE"`)
- **Do not** add extension modules (`_opensearch`, `_redis`, `_redshift`) unless discovery opted in

Leave `terraform_sync.status: pending` until the human reviews the generated file;
`ensure_terraform_module.py` may flip it to `enforced` — revert to pending if the
human has not reviewed yet.

## Never

- Patch `iac/terraform/main.tf` for a new workload
- Hard-code workload names in `.github/workflows/deploy.yml` (it discovers modules)
