# Terraform Apply Guide — workload pipelines

> Apply in a **sandbox** account only. Prefer **`python tools/provision_sandbox.py`**
> for full sandbox bring-up or **`python tools/deploy_workload.py`** for a single workload.
> Tear down with **`python tools/destroy_sandbox.py --yes`** — see `docs/SANDBOX_LIFECYCLE.md`.

## Structure
```
iac/terraform/
├── main.tf                          # root: instantiates the module twice + shared budget
├── variables.tf / outputs.tf
├── terraform.tfvars.example
├── modules/workload_pipeline/       # reusable: KMS, Glue DB+jobs, Lambdas, SFN, Scheduler, SNS, IAM
│   ├── variables.tf
│   ├── main.tf                      # KMS, Glue database, SNS, SFN role+state machine, Scheduler
│   ├── glue.tf                      # Glue job IAM role + aws_glue_job (one per pipeline step)
│   ├── lambda.tf                    # Lambda IAM role + aws_lambda_function (register_catalog, post_deploy_verifier)
│   └── outputs.tf
├── modules/{redshift,opensearch,redis}_workload/  # extension (advisory_transactions only, optional)
│   # See docs/EXTENDING_TO_NEW_SERVICES.md.
├── modules/factory_provision/       # Option B — CodeBuild + SFN for Harness-only deploy
└── backend.tf.example               # Optional S3 remote state (copy for local; CodeBuild uses in CI)
```
One `module` block per workload keeps the two pipelines' resources fully
independent (separate KMS keys, IAM roles, SNS topics, schedules) while
sharing one codebase for the underlying resources — add a third workload by
adding a third `module` block in root `main.tf`.

## Prerequisites
- Terraform >= 1.5
- AWS CLI configured with a **sandbox** profile (`aws sts get-caller-identity`)
- A data-lake S3 bucket already created (Environment Setup Agent / Phase 1)
- **Lambda deployment packages already uploaded** to
  `s3://<data_lake_bucket>/lambda-artifacts/<workload>/{register_catalog,post_deploy_verifier}.zip`
  and **workload scripts already synced** to
  `s3://<data_lake_bucket>/workloads/<workload>/...`
  — both are handled by the `package_and_sync` job in `.github/workflows/deploy.yml`
  before `terraform apply` runs. If applying by hand, run that job's steps
  locally first (`aws s3 sync ...` + the lambda zip step) or Glue/Lambda
  resource creation will succeed but the first job run will fail to find the code.

## Steps
```bash
cd iac/terraform
cp terraform.tfvars.example terraform.tfvars   # edit with your sandbox values

terraform init
terraform validate
terraform plan -out tfplan       # review every resource (~45 resources: 2 workloads)
terraform apply tfplan
```

## What gets created (per workload — x2)
| Resource | Purpose |
|---|---|
| 3x KMS CMK + aliases | Zone-scoped encryption (Bronze/Silver/Gold), rotation ON |
| Glue catalog database | `<workload>_db` |
| **5x `aws_glue_job`** | ingest_to_bronze, bronze_to_silver, quality_silver, silver_to_gold, quality_gold |
| **2x `aws_lambda_function`** | register_catalog (LF-Tag apply), post_deploy_verifier |
| Step Functions state machine | The pipeline (from the workload's ASL artifact) |
| EventBridge schedule | advisory_transactions: daily 07:00 UTC · web_events: hourly :05 |
| SNS topic + email sub | Failure + quality-gate alerts |
| IAM roles (4) | Least-privilege for SFN, Scheduler, Glue jobs, Lambdas |

## Extension resources (advisory_transactions only, optional)
`terraform apply` also creates the Redshift/OpenSearch/Redis extension
modules by default (they're instantiated in root `main.tf`). To skip them
(e.g. to keep the sandbox footprint to just the core pilot), comment out the
three `module "advisory_transactions_{redshift,opensearch,redis}"` blocks
before planning. Their Lambda zips (`register_redshift_spectrum.zip`,
`index_gold_to_opensearch.zip`, `cache_quality_scores.zip`) are built by the
same `deploy.yml` `package_and_sync` job. See `docs/EXTENDING_TO_NEW_SERVICES.md`.

Plus **one shared** `aws_budgets_budget` ($25/mo guardrail at 80%, root-level,
covers both workloads' spend since AWS Budgets is account-scoped).

Total: **10 Glue jobs + 4 Lambdas** across both workloads.

## Verify then tear down (same day)
```bash
aws stepfunctions start-execution \
  --state-machine-arn "$(terraform output -json state_machine_arns | jq -r .advisory_transactions)"

# ... confirm success in the console / CloudWatch ...

terraform destroy      # or: python tools/destroy_sandbox.py --yes (tags + AgentCore + MCP)
```

## Cost note
No always-on compute is provisioned. Cost during the pilot is essentially S3 +
KMS (pennies) plus per-run Glue DPU-seconds when a pipeline actually executes
(quality-gate jobs use 0.0625-DPU Python Shell, not full Spark, to keep runs
cheap) plus near-zero Lambda invocation cost.
