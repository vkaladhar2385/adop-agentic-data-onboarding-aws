# DevOps IaC Agent — Terraform module block from compute.yaml

You are a **sub-agent**. Return **HCL** for the main agent to insert into
`iac/terraform/main.tf`. No `terraform apply`, no AWS, no MCP.

## Inputs

- Workload name
- `workloads/{name}/config/compute.yaml` (`pipeline_steps`, `profile`)
- `workloads/{name}/config/source.yaml` (cadence, compliance)
- `workloads/{name}/config/schedule.yaml` (cron)
- Reference module: `module "advisory_transactions"` in `iac/terraform/main.tf`

## Output

A `module "{workload}"` block using `source = "./modules/workload_pipeline"`:

- `glue_jobs` keys **must** match `pipeline_steps` (`job_type` + `script_path`)
- `glueetl` steps: include `--database` (and `--silver_table` on bronze_to_silver)
- `quality_*` pythonshell: `--zone` and `--data_lake_bucket = var.data_lake_bucket`
- `lambda_functions`: `register_catalog` + `post_deploy_verifier` (same handlers pattern as advisory)
- `schedule_expression` from `schedule.yaml`
- `state_machine_input` landing/bronze/silver/gold prefixes under `var.data_lake_bucket`
- `compliance_tag` from source.yaml regulation (`none` → `"none"`)
- **Do not** add `module "{workload}_opensearch"` or `_redis` unless discovery opted in
- Redshift extension module only if `enable_redshift` / Phase 1 sinks said Redshift

## After the main agent writes HCL

```bash
python tools/validate_compute.py --workload {name}
```

Leave `terraform_sync.status: pending` until the human reviews the block; then flip to `enforced`.
